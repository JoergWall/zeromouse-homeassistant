"""Async client for the ZeroMOUSE cloud API.

The API is not documented publicly; everything here was reverse engineered from the
official app (see API.md in the repository root). This module deliberately does not
import Home Assistant so it can be used from the command line tool as well.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import logging
import math
import time
from typing import Any
from urllib.parse import quote

import aiohttp
from botocore.auth import S3SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from yarl import URL

from .const import (
    GRAPHQL_URL,
    IDENTITY_POOL_ID,
    IMAGE_BUCKET,
    REGION,
    REST_BASE_URL,
    USER_POOL_CLIENT_ID,
    USER_POOL_ID,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_TOKEN_REFRESH_MARGIN = 300  # seconds

_AUTH_ERROR_CODES = {
    "NotAuthorizedException",
    "UserNotFoundException",
    "UserNotConfirmedException",
    "PasswordResetRequiredException",
}

FLAP_FIELDS = """
    deviceID
    name
    model
    networkName
    ownerID
    verHardware
    verMajor
    verMinor
    verRevision
    bootCount
    eventCount
    ai_score
    userFeedback_score
    catClusters {
      id
      name
      allowEntry
      embedding
      threshold
    }
    blockUnknownCats
    createdAt
    updatedAt
"""

QUERY_LIST_FLAPS = f"""
query listFlapByOwnerID($ownerID: String!, $limit: Int, $nextToken: String) {{
  listFlapByOwnerID(ownerID: $ownerID, limit: $limit, nextToken: $nextToken) {{
    items {{ {FLAP_FIELDS} }}
    nextToken
  }}
}}
"""

MUTATION_UPDATE_FLAP = f"""
mutation UpdateMbrPtfFlapData($input: UpdateMbrPtfFlapDataInput!) {{
  updateMbrPtfFlapData(input: $input) {{ {FLAP_FIELDS} }}
}}
"""

EVENT_FIELDS = """
    eventID
    eventTime
    type
    deviceID
    ownerID
    isSeen
    isFlagged
    isHidden
    isDeleted
    isFavorite
    titleImageIndex
    classification_byNet
    catClusterId
    catClusterId_byUser
    createdAt
    updatedAt
"""

QUERY_LIST_EVENTS = f"""
query listEventbyDeviceChrono(
  $deviceID: String!
  $sortDirection: ModelSortDirection
  $limit: Int
  $nextToken: String
) {{
  listEventbyDeviceChrono(
    deviceID: $deviceID
    sortDirection: $sortDirection
    limit: $limit
    nextToken: $nextToken
  ) {{
    items {{
      {EVENT_FIELDS}
      images {{
        classification_byNet
        classification_byReviewer
        imageIndex
        milliseconds
      }}
    }}
    nextToken
  }}
}}
"""

# isFlagged as the app writes it ("Richtig" / "Falsch", tapped again: 0); see API.md
EVENT_FLAG_NONE = 0
EVENT_FLAG_CORRECT = 2
EVENT_FLAG_INCORRECT = 1
RATING_CORRECT = "correct"
RATING_INCORRECT = "incorrect"
_RATING_FLAGS = {RATING_CORRECT: EVENT_FLAG_CORRECT, RATING_INCORRECT: EVENT_FLAG_INCORRECT}

MUTATION_UPDATE_EVENT = """
mutation UpdateMbrPtfEventData(
  $input: UpdateMbrPtfEventDataInput!
  $condition: ModelMbrPtfEventDataConditionInput
) {
  updateMbrPtfEventData(input: $input, condition: $condition) {
    eventID
    deviceID
    isFlagged
    isDeleted
    isFavorite
  }
}
"""

# Only change events that exist: an update must never create an event
_EXISTING_EVENT = {"eventTime": {"attributeExists": True}}

QUERY_LIST_FAVORITES = f"""
query listEventbyFavoriteChrono(
  $deviceID: String!
  $sortDirection: ModelSortDirection
  $limit: Int
  $nextToken: String
) {{
  listEventbyFavoriteChrono(
    deviceID: $deviceID
    sortDirection: $sortDirection
    limit: $limit
    nextToken: $nextToken
  ) {{
    items {{
      {EVENT_FIELDS}
      images {{
        classification_byNet
        classification_byReviewer
        imageIndex
        milliseconds
      }}
    }}
    nextToken
  }}
}}
"""

SUBSCRIPTION_NEW_EVENT = f"""
subscription OnCreateMbrPtfEventData {{
  onCreateMbrPtfEventData {{ {EVENT_FIELDS} }}
}}
"""


class ZeroMouseError(Exception):
    """Base error."""


class ZeroMouseAuthError(ZeroMouseError):
    """Credentials rejected or session expired for good."""


class ZeroMouseApiError(ZeroMouseError):
    """Unexpected API response."""


def jwt_claims(token: str) -> dict[str, Any]:
    """Decode the payload of a JWT without verifying it."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload))
    return claims


# Passed to pycognito's AWSSRP so that it does not create a boto3 client.
_NO_BOTO_CLIENT = object()


async def _default_executor(func: Callable[..., Any], *args: Any) -> Any:
    return await asyncio.get_running_loop().run_in_executor(None, func, *args)


class ZeroMouseApi:
    """ZeroMOUSE cloud client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        executor: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        """Initialize the client.

        ``executor`` runs the CPU heavy SRP math off the event loop; Home Assistant
        passes ``hass.async_add_executor_job``.
        """
        self._session = session
        self._email = email
        self._password = password
        self._executor = executor or _default_executor
        self._id_token: str | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_exp = 0.0
        self._token_lock = asyncio.Lock()
        self._identity_id: str | None = None
        self._aws_credentials: Credentials | None = None
        self._aws_credentials_exp = 0.0
        self._aws_lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth

    @property
    def owner_id(self) -> str:
        """Cognito ``sub`` of the logged in user (``ownerID`` in the API)."""
        if self._id_token is None:
            raise ZeroMouseAuthError("Not logged in")
        return str(jwt_claims(self._id_token)["sub"])

    async def async_login(self) -> None:
        """Log in with email and password (SRP)."""
        async with self._token_lock:
            await self._async_login()

    async def async_get_tokens(self) -> tuple[str, str]:
        """Return a valid (id_token, access_token) pair, refreshing if needed."""
        async with self._token_lock:
            if self._refresh_token is None:
                await self._async_login()
            elif time.time() > self._token_exp - _TOKEN_REFRESH_MARGIN:
                await self._async_refresh()
            assert self._id_token is not None and self._access_token is not None
            return self._id_token, self._access_token

    def _invalidate_tokens(self) -> None:
        self._token_exp = 0.0

    async def _cognito_idp(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call the Cognito user pool API (JSON protocol, no AWS signature needed)."""
        try:
            async with self._session.post(
                f"https://cognito-idp.{REGION}.amazonaws.com/",
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": f"AWSCognitoIdentityProviderService.{action}",
                },
                data=json.dumps(payload),
                timeout=_TIMEOUT,
            ) as resp:
                result: dict[str, Any] = await resp.json(content_type=None)
                status = resp.status
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ZeroMouseApiError(f"Cognito {action}: {err}") from err
        if status >= 400:
            code = str(result.get("__type", "")).rsplit("#", 1)[-1]
            if code in _AUTH_ERROR_CODES:
                raise ZeroMouseAuthError(code)
            raise ZeroMouseApiError(f"Cognito {action}: {code}: {result.get('message')}")
        return result

    def _new_srp(self) -> Any:
        # Only the SRP math of pycognito is used; the network calls are ours.
        from pycognito.aws_srp import AWSSRP  # noqa: PLC0415

        return AWSSRP(
            username=self._email,
            password=self._password,
            pool_id=USER_POOL_ID,
            client_id=USER_POOL_CLIENT_ID,
            client=_NO_BOTO_CLIENT,
        )

    async def _async_login(self) -> None:
        srp = await self._executor(self._new_srp)
        auth_params = srp.get_auth_params()
        response = await self._cognito_idp(
            "InitiateAuth",
            {
                "AuthFlow": "USER_SRP_AUTH",
                "ClientId": USER_POOL_CLIENT_ID,
                "AuthParameters": auth_params,
            },
        )
        if response.get("ChallengeName") != "PASSWORD_VERIFIER":
            raise ZeroMouseAuthError(
                f"Unsupported login challenge {response.get('ChallengeName')}"
            )
        challenge = await self._executor(
            srp.process_challenge, response["ChallengeParameters"], auth_params
        )
        tokens = await self._cognito_idp(
            "RespondToAuthChallenge",
            {
                "ClientId": USER_POOL_CLIENT_ID,
                "ChallengeName": "PASSWORD_VERIFIER",
                "ChallengeResponses": challenge,
            },
        )
        if "AuthenticationResult" not in tokens:
            # NEW_PASSWORD_REQUIRED, MFA, ... need the app
            raise ZeroMouseAuthError(
                f"Login needs an interactive challenge: {tokens.get('ChallengeName')}"
            )
        self._store_tokens(tokens["AuthenticationResult"])

    async def _async_refresh(self) -> None:
        try:
            result = await self._cognito_idp(
                "InitiateAuth",
                {
                    "AuthFlow": "REFRESH_TOKEN_AUTH",
                    "ClientId": USER_POOL_CLIENT_ID,
                    "AuthParameters": {"REFRESH_TOKEN": self._refresh_token},
                },
            )
        except ZeroMouseAuthError as err:
            _LOGGER.debug("Token refresh failed (%s), logging in again", err)
            await self._async_login()
            return
        self._store_tokens(result["AuthenticationResult"])

    def _store_tokens(self, result: dict[str, Any]) -> None:
        self._id_token = result["IdToken"]
        self._access_token = result["AccessToken"]
        if result.get("RefreshToken"):
            self._refresh_token = result["RefreshToken"]
        self._token_exp = float(jwt_claims(result["AccessToken"])["exp"])

    # ------------------------------------------------------------ transports

    async def _rest(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        for attempt in range(2):
            id_token, _ = await self.async_get_tokens()
            try:
                async with self._session.request(
                    method,
                    f"{REST_BASE_URL}{path}",
                    headers={"auth-token": id_token},
                    json=body,
                    timeout=_TIMEOUT,
                ) as resp:
                    text = await resp.text()
                    if resp.status in (401, 403) and attempt == 0:
                        self._invalidate_tokens()
                        continue
                    if resp.status in (401, 403):
                        raise ZeroMouseAuthError(f"{method} {path}: HTTP {resp.status}")
                    if resp.status >= 400:
                        raise ZeroMouseApiError(
                            f"{method} {path}: HTTP {resp.status}: {text[:300]}"
                        )
            except (aiohttp.ClientError, TimeoutError) as err:
                raise ZeroMouseApiError(f"{method} {path}: {err}") from err
            if not text:
                return None
            try:
                return json.loads(text)
            except ValueError:
                return text
        raise ZeroMouseApiError("unreachable")

    async def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run a GraphQL operation against AppSync."""
        for attempt in range(2):
            _, access_token = await self.async_get_tokens()
            try:
                async with self._session.post(
                    GRAPHQL_URL,
                    headers={"Authorization": access_token},
                    json={"query": query, "variables": variables or {}},
                    timeout=_TIMEOUT,
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        self._invalidate_tokens()
                        continue
                    if resp.status == 401:
                        raise ZeroMouseAuthError("GraphQL: HTTP 401")
                    payload = await resp.json(content_type=None)
                    status = resp.status
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise ZeroMouseApiError(f"GraphQL: {err}") from err
            if not isinstance(payload, dict) or (
                "data" not in payload and "errors" not in payload
            ):
                raise ZeroMouseApiError(f"GraphQL: HTTP {status}: {str(payload)[:200]}")
            errors = payload.get("errors")
            if errors and not payload.get("data"):
                if any(e.get("errorType") == "UnauthorizedException" for e in errors):
                    raise ZeroMouseAuthError(str(errors))
                raise ZeroMouseApiError(f"GraphQL errors: {errors}")
            if errors:
                _LOGGER.debug("GraphQL partial errors: %s", errors)
            data: dict[str, Any] = payload["data"]
            return data
        raise ZeroMouseApiError("unreachable")

    # ----------------------------------------------------------------- flaps

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return all ZeroMOUSE devices of the account."""
        devices: list[dict[str, Any]] = []
        next_token = None
        while True:
            data = await self.graphql(
                QUERY_LIST_FLAPS,
                {"ownerID": self.owner_id, "limit": 100, "nextToken": next_token},
            )
            page = data["listFlapByOwnerID"]
            devices.extend(item for item in page["items"] if item)
            next_token = page.get("nextToken")
            if not next_token:
                return devices

    async def async_update_device(self, device_id: str, **fields: Any) -> dict[str, Any]:
        """Update flap data, e.g. ``blockUnknownCats`` or ``catClusters``."""
        data = await self.graphql(
            MUTATION_UPDATE_FLAP, {"input": {"deviceID": device_id, **fields}}
        )
        flap: dict[str, Any] = data["updateMbrPtfFlapData"]
        return flap

    # ---------------------------------------------------------------- shadow

    async def async_get_shadow(self, device_id: str) -> dict[str, Any]:
        """Return the AWS IoT device shadow ({"state": {"reported", "desired"}})."""
        shadow = await self._rest("GET", f"/device-shadow/?deviceID={quote(device_id)}")
        if isinstance(shadow, dict) and "state" not in shadow:
            # Be tolerant towards wrapped responses
            for key in ("shadow", "data", "body"):
                inner = shadow.get(key)
                if isinstance(inner, str):
                    inner = json.loads(inner)
                if isinstance(inner, dict) and "state" in inner:
                    return inner
        return shadow if isinstance(shadow, dict) else {}

    async def async_update_shadow(self, device_id: str, desired: dict[str, Any]) -> Any:
        """Patch the desired shadow state, e.g. {"system": {"undecidableMode": 1}}."""
        return await self._rest(
            "PATCH", f"/device-shadow/?deviceID={quote(device_id)}", desired
        )

    async def async_set_entry_mode(self, device_id: str, mode: int) -> Any:
        """Set the entry mode (0 free, 1 block prey, 2 face detection, 3 locked)."""
        return await self._rest(
            "PATCH", f"/block-modes/?deviceID={quote(device_id)}", {"blockModeIn": mode}
        )

    async def async_set_exit_mode(
        self, device_id: str, mode: int, open_at: int, close_at: int
    ) -> Any:
        """Set exit mode (0 open, 1 locked, 2 time based; times in min after 00:00)."""
        return await self._rest(
            "PATCH",
            f"/block-modes/?deviceID={quote(device_id)}",
            {"blockModeOut": mode, "outOpenAt": open_at, "outCloseAt": close_at},
        )

    # ------------------------------------------------------- stats and user

    async def async_get_statistics(self, device_id: str) -> dict[str, Any]:
        """Return {"stats": {"prey_monthly": [{"period": "YYYY-MM", "value": n}]}}."""
        return await self._rest("GET", f"/statistics/{quote(device_id)}") or {}

    async def async_get_user(self) -> dict[str, Any]:
        """Return the user profile."""
        return await self._rest("GET", "/user/") or {}

    # ---------------------------------------------------------------- events

    async def async_get_events_page(
        self,
        device_id: str,
        next_token: str | None = None,
        limit: int = 100,
        favorites: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return one page of events (newest first) and the token of the next page.

        ``favorites`` uses the app's favourites index, which only holds favourites.
        Deleted events are included; callers filter them.
        """
        query, field = (
            (QUERY_LIST_FAVORITES, "listEventbyFavoriteChrono")
            if favorites
            else (QUERY_LIST_EVENTS, "listEventbyDeviceChrono")
        )
        data = await self.graphql(
            query,
            {
                "deviceID": device_id,
                "sortDirection": "DESC",
                "limit": limit,
                "nextToken": next_token,
            },
        )
        page = data.get(field)
        if not isinstance(page, dict):
            raise ZeroMouseApiError(f"{field}: no data")
        items = [e for e in page.get("items") or [] if e]
        return items, page.get("nextToken")

    async def async_update_event(
        self, device_id: str, event_id: str, **fields: Any
    ) -> dict[str, Any]:
        """Change fields of an existing event (rating, deleted, favourite)."""
        data = await self.graphql(
            MUTATION_UPDATE_EVENT,
            {
                "input": {"eventID": event_id, "deviceID": device_id, **fields},
                "condition": _EXISTING_EVENT,
            },
        )
        event = data.get("updateMbrPtfEventData")
        if not isinstance(event, dict):
            raise ZeroMouseApiError(f"Event {event_id} could not be changed")
        return event

    async def async_rate_event(
        self, device_id: str, event_id: str, rating: str | None
    ) -> None:
        """Rate the classification like "Richtig" / "Falsch" in the app.

        ``rating`` is "correct", "incorrect" or None to remove the rating.
        """
        await self.async_update_event(
            device_id, event_id, isFlagged=_RATING_FLAGS.get(rating or "", EVENT_FLAG_NONE)
        )

    async def async_delete_event(self, device_id: str, event_id: str) -> None:
        """Delete an event like the app: the cloud only marks it as deleted."""
        await self.async_update_event(device_id, event_id, isDeleted=1)

    async def async_get_events(
        self, device_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return the newest events of a device, newest first."""
        items, _ = await self.async_get_events_page(device_id, limit=limit)
        return [e for e in items if not e.get("isDeleted")]

    async def async_get_events_since(
        self, device_id: str, since: datetime, max_items: int = 1000
    ) -> list[dict[str, Any]]:
        """Return all events newer than ``since``, newest first (paginated)."""
        events: list[dict[str, Any]] = []
        next_token = None
        while len(events) < max_items:
            items, next_token = await self.async_get_events_page(device_id, next_token)
            reached_end = False
            for event in items:
                when = parse_event_time(event)
                if when is not None and when < since:
                    reached_end = True
                    break
                if not event.get("isDeleted"):
                    events.append(event)
            if reached_end or not next_token:
                break
        return events[:max_items]

    # ---------------------------------------------------------------- images

    async def _cognito_identity(
        self, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                f"https://cognito-identity.{REGION}.amazonaws.com/",
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": f"AWSCognitoIdentityService.{action}",
                },
                data=json.dumps(payload),
                timeout=_TIMEOUT,
            ) as resp:
                try:
                    result = await resp.json(content_type=None)
                except ValueError:
                    result = None
                if resp.status >= 400 or not isinstance(result, dict):
                    # The AWS message names the identity id: keep only the error type
                    kind = result.get("__type") if isinstance(result, dict) else None
                    raise ZeroMouseApiError(f"Cognito identity {action}: HTTP {resp.status} {kind}")
                return result
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ZeroMouseApiError(f"Cognito identity {action}: {err}") from err

    async def _async_aws_credentials(self) -> tuple[str, Credentials]:
        async with self._aws_lock:
            if (
                self._aws_credentials is not None
                and self._identity_id is not None
                and time.time() < self._aws_credentials_exp - _TOKEN_REFRESH_MARGIN
            ):
                return self._identity_id, self._aws_credentials
            id_token, _ = await self.async_get_tokens()
            logins = {f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token}
            if self._identity_id is None:
                result = await self._cognito_identity(
                    "GetId", {"IdentityPoolId": IDENTITY_POOL_ID, "Logins": logins}
                )
                self._identity_id = result["IdentityId"]
            result = await self._cognito_identity(
                "GetCredentialsForIdentity",
                {"IdentityId": self._identity_id, "Logins": logins},
            )
            creds = result["Credentials"]
            self._aws_credentials = Credentials(
                creds["AccessKeyId"], creds["SecretKey"], creds["SessionToken"]
            )
            self._aws_credentials_exp = float(creds["Expiration"])
            return self._identity_id, self._aws_credentials

    async def async_get_event_image(
        self, device_id: str, event_id: str, image_index: int
    ) -> bytes | None:
        """Download one JPEG of an event, None if it does not exist."""
        identity_id, credentials = await self._async_aws_credentials()
        key = (
            f"private/{identity_id}/devices/{device_id}/events/{event_id}"
            f"/images/{image_index}.jpg"
        )
        url = f"https://{IMAGE_BUCKET}.s3.{REGION}.amazonaws.com/{quote(key, safe='/')}"
        # Messages name the picture without the key (it contains the identity id)
        name = f"{event_id}/{image_index}"
        request = AWSRequest(method="GET", url=url)
        S3SigV4Auth(credentials, "s3", REGION).add_auth(request)
        try:
            async with self._session.get(
                URL(url, encoded=True), headers=dict(request.headers), timeout=_TIMEOUT
            ) as resp:
                if resp.status in (403, 404):
                    _LOGGER.debug("Image %s not available: HTTP %s", name, resp.status)
                    return None
                if resp.status >= 400:
                    raise ZeroMouseApiError(f"S3 image {name}: HTTP {resp.status}")
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ZeroMouseApiError(f"S3 image {name}: {type(err).__name__}") from err


def event_image_index(event: dict[str, Any]) -> int | None:
    """Return the index of the preview image of an event."""
    if (index := event.get("titleImageIndex")) is not None:
        return int(index)
    images = [i for i in event.get("images") or [] if i and i.get("imageIndex") is not None]
    if images:
        return int(min(images, key=lambda i: i["imageIndex"])["imageIndex"])
    return None


def event_rating(event: dict[str, Any]) -> str | None:
    """Return the user's rating of an event: "correct", "incorrect" or None."""
    flag = event.get("isFlagged")
    return next((rating for rating, f in _RATING_FLAGS.items() if f == flag), None)


def parse_event_time(event: dict[str, Any]) -> datetime | None:
    """Parse ``eventTime`` (epoch s/ms or ISO string), fall back to ``createdAt``."""
    for key in ("eventTime", "createdAt"):
        value = event.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        if not math.isfinite(number):
            continue
        if number > 1e12:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            continue
    return None
