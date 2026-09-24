"""Tests for the ZeroMOUSE API client (HTTP mocked)."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
import json
import re
import time
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.zeromouse.api import (
    ZeroMouseApi,
    ZeroMouseApiError,
    ZeroMouseAuthError,
    _default_executor,
    event_image_index,
    jwt_claims,
    parse_event_time,
)
from custom_components.zeromouse.const import GRAPHQL_URL, REST_BASE_URL

IDP_URL = "https://cognito-idp.eu-central-1.amazonaws.com/"
IDENTITY_URL = "https://cognito-identity.eu-central-1.amazonaws.com/"
S3_PREFIX = "https://mbr-ptf-images-eu-central-1-dev.s3.eu-central-1.amazonaws.com/"


def make_jwt(**claims: Any) -> str:
    """Build an unsigned JWT."""
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


def auth_result(exp: float | None = None, refresh: bool = True) -> dict[str, Any]:
    """Return a Cognito AuthenticationResult."""
    exp = exp or time.time() + 3600
    result = {
        "IdToken": make_jwt(sub="owner-1", exp=exp),
        "AccessToken": make_jwt(sub="owner-1", exp=exp),
    }
    if refresh:
        result["RefreshToken"] = "refresh-1"
    return {"AuthenticationResult": result}


class FakeSrp:
    """Replacement for pycognito's AWSSRP."""

    def get_auth_params(self) -> dict[str, str]:
        return {"USERNAME": "a@b.c", "SRP_A": "aa"}

    def process_challenge(self, challenge: dict, params: dict) -> dict[str, str]:
        assert challenge["SALT"] == "salt"
        return {"USERNAME": "user", "PASSWORD_CLAIM_SIGNATURE": "sig"}


def cognito_side_effect(
    login: dict | None = None,
    respond: dict | None = None,
    refresh: dict | None = None,
    status: dict[str, int] | None = None,
) -> Any:
    """Dispatch Cognito calls on the JSON payload."""
    status = status or {}

    async def _side_effect(method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        payload = json.loads(data)
        if payload.get("AuthFlow") == "USER_SRP_AUTH":
            key, body = "login", login or {
                "ChallengeName": "PASSWORD_VERIFIER",
                "ChallengeParameters": {"SALT": "salt"},
            }
        elif payload.get("AuthFlow") == "REFRESH_TOKEN_AUTH":
            key, body = "refresh", refresh or auth_result(refresh=False)
        else:
            key, body = "respond", respond or auth_result()
        return AiohttpClientMockResponse(
            "post", url, status=status.get(key, 200), json=body
        )

    return _side_effect


@pytest.fixture
async def mocker() -> AiohttpClientMocker:
    """Return a request mocker."""
    return AiohttpClientMocker()


@pytest.fixture
async def session(mocker: AiohttpClientMocker) -> aiohttp.ClientSession:
    """Return a mocked session."""
    session = mocker.create_session(asyncio.get_running_loop())
    yield session
    await session.close()


@pytest.fixture
def api(session: aiohttp.ClientSession) -> ZeroMouseApi:
    """Return an API client with fake SRP."""
    client = ZeroMouseApi(session, "a@b.c", "pw")
    client._new_srp = FakeSrp  # type: ignore[method-assign]
    return client


async def logged_in(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> ZeroMouseApi:
    """Log the client in."""
    mocker.post(IDP_URL, side_effect=cognito_side_effect())
    await api.async_login()
    return api


# ------------------------------------------------------------------ auth


async def test_login_and_refresh(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test SRP login, token reuse and refresh."""
    with pytest.raises(ZeroMouseAuthError):
        _ = api.owner_id
    await logged_in(api, mocker)
    assert api.owner_id == "owner-1"
    assert mocker.call_count == 2  # InitiateAuth + RespondToAuthChallenge

    await api.async_get_tokens()
    assert mocker.call_count == 2  # cached

    api._token_exp = 0
    await api.async_get_tokens()
    assert mocker.call_count == 3  # refresh
    assert api._refresh_token == "refresh-1"  # kept


async def test_get_tokens_logs_in(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test that the first token request logs in."""
    mocker.post(IDP_URL, side_effect=cognito_side_effect())
    id_token, access = await api.async_get_tokens()
    assert jwt_claims(id_token)["sub"] == "owner-1"
    assert access


async def test_refresh_failure_logs_in_again(
    api: ZeroMouseApi, mocker: AiohttpClientMocker
) -> None:
    """Test fallback to a full login when the refresh token is rejected."""
    mocker.post(
        IDP_URL,
        side_effect=cognito_side_effect(
            refresh={"__type": "NotAuthorizedException"}, status={"refresh": 400}
        ),
    )
    await api.async_login()
    api._token_exp = 0
    await api.async_get_tokens()
    assert mocker.call_count == 5  # login(2) + refresh + login(2)


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"login": {"__type": "NotAuthorizedException"}, "status": {"login": 400}}, ZeroMouseAuthError),
        ({"login": {"__type": "x#UserNotFoundException"}, "status": {"login": 400}}, ZeroMouseAuthError),
        ({"login": {"__type": "TooManyRequestsException"}, "status": {"login": 400}}, ZeroMouseApiError),
        ({"login": {"ChallengeName": "CUSTOM_CHALLENGE"}}, ZeroMouseAuthError),
        ({"respond": {"ChallengeName": "SMS_MFA"}}, ZeroMouseAuthError),
    ],
)
async def test_login_errors(
    api: ZeroMouseApi, mocker: AiohttpClientMocker, kwargs: dict, error: type
) -> None:
    """Test login failures."""
    mocker.post(IDP_URL, side_effect=cognito_side_effect(**kwargs))
    with pytest.raises(error):
        await api.async_login()


async def test_login_network_error(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test a network error during login."""
    mocker.post(IDP_URL, exc=aiohttp.ClientError("boom"))
    with pytest.raises(ZeroMouseApiError):
        await api.async_login()


async def test_real_srp_object(session: aiohttp.ClientSession) -> None:
    """Test that pycognito's SRP helper is created without a boto3 client."""
    client = ZeroMouseApi(session, "a@b.c", "pw")
    srp = await _default_executor(client._new_srp)
    assert srp.get_auth_params()["USERNAME"] == "a@b.c"


# ------------------------------------------------------------------ REST


async def test_rest_calls(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test REST endpoints and the auth-token header."""
    await logged_in(api, mocker)
    mocker.get(f"{REST_BASE_URL}/device-shadow/?deviceID=d1", json={"state": {"reported": {}}})
    mocker.get(f"{REST_BASE_URL}/statistics/d1", json={"stats": {}})
    mocker.get(f"{REST_BASE_URL}/user/", text="")
    mocker.patch(f"{REST_BASE_URL}/device-shadow/?deviceID=d1", text="ok")
    mocker.patch(f"{REST_BASE_URL}/block-modes/?deviceID=d1", json={"ok": True})

    assert await api.async_get_shadow("d1") == {"state": {"reported": {}}}
    assert await api.async_get_statistics("d1") == {"stats": {}}
    assert await api.async_get_user() == {}
    assert await api.async_update_shadow("d1", {"system": {"undecidableMode": 1}}) == "ok"
    assert await api.async_set_entry_mode("d1", 2) == {"ok": True}
    assert await api.async_set_exit_mode("d1", 2, 480, 1200) == {"ok": True}

    method, url, data, headers = mocker.mock_calls[-1]
    assert method == "PATCH"
    assert data == {"blockModeOut": 2, "outOpenAt": 480, "outCloseAt": 1200}
    assert headers["auth-token"].count(".") == 2


@pytest.mark.parametrize(
    "body",
    [
        {"shadow": json.dumps({"state": {"reported": {"a": 1}}})},
        {"data": {"state": {"reported": {"a": 1}}}},
    ],
)
async def test_shadow_wrapped(
    api: ZeroMouseApi, mocker: AiohttpClientMocker, body: dict
) -> None:
    """Test tolerance for wrapped shadow responses."""
    await logged_in(api, mocker)
    mocker.get(f"{REST_BASE_URL}/device-shadow/?deviceID=d1", json=body)
    assert await api.async_get_shadow("d1") == {"state": {"reported": {"a": 1}}}


async def test_shadow_not_a_dict(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test an unexpected shadow response."""
    await logged_in(api, mocker)
    mocker.get(f"{REST_BASE_URL}/device-shadow/?deviceID=d1", json=[1])
    assert await api.async_get_shadow("d1") == {}


async def test_rest_retry_after_401(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test that a 401 refreshes the token once."""
    await logged_in(api, mocker)
    calls = 0

    async def _side_effect(method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        nonlocal calls
        calls += 1
        return AiohttpClientMockResponse(
            "get", url, status=401 if calls == 1 else 200, json={"stats": {}}
        )

    mocker.get(f"{REST_BASE_URL}/statistics/d1", side_effect=_side_effect)
    assert await api.async_get_statistics("d1") == {"stats": {}}
    assert calls == 2


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 403}, ZeroMouseAuthError),
        ({"status": 500, "text": "oops"}, ZeroMouseApiError),
        ({"exc": aiohttp.ClientError()}, ZeroMouseApiError),
        ({"exc": TimeoutError()}, ZeroMouseApiError),
    ],
)
async def test_rest_errors(
    api: ZeroMouseApi, mocker: AiohttpClientMocker, kwargs: dict, error: type
) -> None:
    """Test REST error handling."""
    await logged_in(api, mocker)
    mocker.get(f"{REST_BASE_URL}/user/", **kwargs)
    with pytest.raises(error):
        await api.async_get_user()


# --------------------------------------------------------------- GraphQL


async def test_graphql_devices_and_events(
    api: ZeroMouseApi, mocker: AiohttpClientMocker
) -> None:
    """Test GraphQL queries incl. pagination."""
    await logged_in(api, mocker)
    pages = iter(
        [
            {"data": {"listFlapByOwnerID": {"items": [{"deviceID": "d1"}, None], "nextToken": "t"}}},
            {"data": {"listFlapByOwnerID": {"items": [{"deviceID": "d2"}], "nextToken": None}}},
            {"data": {"listEventbyDeviceChrono": {"items": [{"eventID": "e1"}, {"eventID": "e0", "isDeleted": 1}, None]}}},
            {"data": {"updateMbrPtfFlapData": {"deviceID": "d1"}}, "errors": [{"message": "partial"}]},
        ]
    )

    async def _side_effect(method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        return AiohttpClientMockResponse("post", url, json=next(pages))

    mocker.post(GRAPHQL_URL, side_effect=_side_effect)
    assert [d["deviceID"] for d in await api.async_get_devices()] == ["d1", "d2"]
    assert [e["eventID"] for e in await api.async_get_events("d1", 5)] == ["e1"]
    assert await api.async_update_device("d1", blockUnknownCats=True) == {"deviceID": "d1"}
    variables = mocker.mock_calls[-1][2]["variables"]
    assert variables == {"input": {"deviceID": "d1", "blockUnknownCats": True}}


async def test_events_since_pagination(api: ZeroMouseApi) -> None:
    """Test that async_get_events_since pages until the start time."""
    pages = [
        {"listEventbyDeviceChrono": {"items": [{"eventID": "3", "eventTime": 300}, None, {"eventID": "2", "eventTime": 200}], "nextToken": "t"}},
        {"listEventbyDeviceChrono": {"items": [{"eventID": "1", "eventTime": 100, "isDeleted": 1}, {"eventID": "0", "eventTime": 50}], "nextToken": "t2"}},
    ]
    with patch.object(api, "graphql", side_effect=pages) as graphql:
        events = await api.async_get_events_since("d", datetime.fromtimestamp(90, UTC))
    assert [e["eventID"] for e in events] == ["3", "2"]
    assert graphql.await_count == 2


async def test_graphql_retry_and_errors(
    api: ZeroMouseApi, mocker: AiohttpClientMocker
) -> None:
    """Test GraphQL auth retry and error mapping."""
    await logged_in(api, mocker)
    responses = iter(
        [
            (401, {}),
            (200, {"data": {"listFlapByOwnerID": {"items": []}}}),
            (401, {}),
            (401, {}),
            (200, {"data": None, "errors": [{"errorType": "UnauthorizedException"}]}),
            (200, {"data": None, "errors": [{"errorType": "Other"}]}),
        ]
    )

    async def _side_effect(method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        status, body = next(responses)
        return AiohttpClientMockResponse("post", url, status=status, json=body)

    mocker.post(GRAPHQL_URL, side_effect=_side_effect)
    assert await api.async_get_devices() == []
    for error in (ZeroMouseAuthError, ZeroMouseAuthError, ZeroMouseApiError):
        with pytest.raises(error):
            await api.async_get_devices()


async def test_graphql_network_error(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test a network error in GraphQL."""
    await logged_in(api, mocker)
    mocker.post(GRAPHQL_URL, exc=aiohttp.ClientError())
    with pytest.raises(ZeroMouseApiError):
        await api.async_get_devices()


# ---------------------------------------------------------------- images


async def test_event_image(api: ZeroMouseApi, mocker: AiohttpClientMocker) -> None:
    """Test identity pool credentials and the signed S3 request."""
    await logged_in(api, mocker)

    async def _identity(method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        payload = json.loads(data)
        body = (
            {"IdentityId": "eu-central-1:abc"}
            if "IdentityPoolId" in payload
            else {
                "Credentials": {
                    "AccessKeyId": "AK",
                    "SecretKey": "SK",
                    "SessionToken": "ST",
                    "Expiration": time.time() + 3600,
                }
            }
        )
        return AiohttpClientMockResponse("post", url, json=body)

    mocker.post(IDENTITY_URL, side_effect=_identity)
    mocker.get(
        re.compile(r"eu-central-1%3Aabc/devices/d1/events/e1/images/3\.jpg$"),
        content=b"jpeg",
    )
    mocker.get(
        re.compile(r"eu-central-1%3Aabc/devices/d1/events/e1/images/4\.jpg$"),
        status=404,
    )
    mocker.get(
        re.compile(r"eu-central-1%3Aabc/devices/d1/events/e1/images/5\.jpg$"),
        status=500,
    )
    mocker.get(
        re.compile(r"eu-central-1%3Aabc/devices/d1/events/e1/images/6\.jpg$"),
        exc=aiohttp.ClientError(),
    )
    assert await api.async_get_event_image("d1", "e1", 3) == b"jpeg"
    headers = mocker.mock_calls[-1][3]
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/")
    assert headers["X-Amz-Security-Token"] == "ST"
    identity_calls = sum(1 for c in mocker.mock_calls if str(c[1]) == IDENTITY_URL)

    assert await api.async_get_event_image("d1", "e1", 4) is None
    with pytest.raises(ZeroMouseApiError):
        await api.async_get_event_image("d1", "e1", 5)
    with pytest.raises(ZeroMouseApiError):
        await api.async_get_event_image("d1", "e1", 6)
    # Credentials were reused
    assert sum(1 for c in mocker.mock_calls if str(c[1]) == IDENTITY_URL) == identity_calls == 2


@pytest.mark.parametrize(
    "kwargs", [{"status": 400, "json": {"__type": "NotAuthorized"}}, {"exc": aiohttp.ClientError()}]
)
async def test_identity_errors(
    api: ZeroMouseApi, mocker: AiohttpClientMocker, kwargs: dict
) -> None:
    """Test identity pool failures."""
    await logged_in(api, mocker)
    mocker.post(IDENTITY_URL, **kwargs)
    with pytest.raises(ZeroMouseApiError):
        await api.async_get_event_image("d1", "e1", 0)


# --------------------------------------------------------------- helpers


def test_helpers() -> None:
    """Test parsing helpers."""
    assert parse_event_time({"eventTime": 1790000000000}).year == 2026
    assert parse_event_time({"eventTime": "1790000000"}).year == 2026
    assert parse_event_time({"eventTime": "nonsense", "createdAt": "2026-01-02T03:04:05Z"}).month == 1
    assert parse_event_time({"createdAt": "2026-01-02T03:04:05"}).tzinfo is UTC
    assert parse_event_time({"eventTime": ""}) is None
    assert parse_event_time({}) is None
    assert event_image_index({"images": [{"imageIndex": 3}, {"imageIndex": 1}]}) == 1
    assert event_image_index({"titleImageIndex": 0}) == 0
    assert event_image_index({"images": [None]}) is None
    assert jwt_claims(make_jwt(sub="x"))["sub"] == "x"


async def test_custom_executor(session: aiohttp.ClientSession) -> None:
    """Test that a custom executor is used for the SRP math."""
    executor = MagicMock(side_effect=lambda func, *args: _default_executor(func, *args))
    client = ZeroMouseApi(session, "a@b.c", "pw", executor=executor)
    assert client._executor is executor
