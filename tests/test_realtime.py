"""Tests for the AppSync realtime subscription."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.zeromouse.realtime import ZeroMouseRealtime


class FakeWs:
    """Fake aiohttp websocket."""

    def __init__(self, messages: list[Any]) -> None:
        self.messages = list(messages)
        self.sent: list[dict] = []

    async def __aenter__(self) -> FakeWs:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def receive(self, timeout: float | None = None) -> Any:
        msg = self.messages.pop(0)
        if isinstance(msg, dict):
            return aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, json.dumps(msg), None)
        return msg


def make_realtime(ws: FakeWs) -> tuple[ZeroMouseRealtime, AsyncMock, MagicMock]:
    """Create a realtime client around a fake websocket."""
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=ws)
    api = MagicMock()
    api.async_get_tokens = AsyncMock(return_value=("id", "access"))
    on_event = AsyncMock()
    return ZeroMouseRealtime(session, api, on_event), on_event, session


async def test_subscription_flow() -> None:
    """Test ack, start, keep-alive, data and error handling."""
    ws = FakeWs(
        [
            {"type": "connection_ack", "payload": {"connectionTimeoutMs": 300000}},
            {"type": "start_ack"},
            aiohttp.WSMessage(aiohttp.WSMsgType.BINARY, b"", None),
            {"type": "ka"},
            {"type": "data", "payload": {"data": {"onCreateMbrPtfEventData": {"eventID": "e1"}}}},
            {"type": "data", "payload": {"data": {}}},
            {"type": "error", "payload": {}},
        ]
    )
    realtime, on_event, session = make_realtime(ws)
    await realtime._run_once()

    url = session.ws_connect.call_args.args[0]
    assert "appsync-realtime-api" in url and "header=" in url
    assert ws.sent[0] == {"type": "connection_init"}
    start = ws.sent[1]
    assert start["type"] == "start"
    assert "onCreateMbrPtfEventData" in json.loads(start["payload"]["data"])["query"]
    assert start["payload"]["extensions"]["authorization"]["Authorization"] == "access"
    on_event.assert_awaited_once_with({"eventID": "e1"})


async def test_socket_closed() -> None:
    """Test that a closed socket ends the connection."""
    ws = FakeWs([aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None)])
    realtime, on_event, _ = make_realtime(ws)
    await realtime._run_once()
    on_event.assert_not_awaited()


async def test_reconnect_after_deadline() -> None:
    """Test the periodic reconnect that renews the token."""
    ws = FakeWs([{"type": "connection_ack"}])
    realtime, _, _ = make_realtime(ws)
    with patch("custom_components.zeromouse.realtime._RECONNECT_AFTER", 0):
        await realtime._run_once()
    assert ws.sent[-1]["type"] == "stop"


async def test_run_retries_with_backoff() -> None:
    """Test that run() keeps reconnecting after errors."""
    realtime, _, _ = make_realtime(FakeWs([]))
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    with (
        patch.object(realtime, "_run_once", AsyncMock(side_effect=RuntimeError)),
        patch("custom_components.zeromouse.realtime.asyncio.sleep", fake_sleep),
        pytest.raises(asyncio.CancelledError),
    ):
        await realtime.run()
    assert sleeps == [5, 10, 20]


async def test_run_does_not_log_the_token(caplog: pytest.LogCaptureFixture) -> None:
    """Test that a failed handshake does not write the token-bearing URL to the log."""
    realtime, _, _ = make_realtime(FakeWs([]))
    url = "wss://x/graphql?header=eyJBdXRob3JpemF0aW9uIjoic2VjcmV0In0=&payload=e30="
    error = RuntimeError(f"401, message='Invalid response status', url='{url}'")

    async def fake_sleep(delay: float) -> None:
        raise asyncio.CancelledError

    caplog.set_level("DEBUG", logger="custom_components.zeromouse.realtime")
    with (
        patch.object(realtime, "_run_once", AsyncMock(side_effect=error)),
        patch("custom_components.zeromouse.realtime.asyncio.sleep", fake_sleep),
        pytest.raises(asyncio.CancelledError),
    ):
        await realtime.run()
    assert "header=<redacted>&payload" in caplog.text
    assert "eyJBdXRo" not in caplog.text


async def test_run_propagates_cancel() -> None:
    """Test that cancelling stops the loop."""
    realtime, _, _ = make_realtime(FakeWs([]))
    with (
        patch.object(realtime, "_run_once", AsyncMock(side_effect=asyncio.CancelledError)),
        pytest.raises(asyncio.CancelledError),
    ):
        await realtime.run()


async def test_run_resets_backoff_after_long_connection() -> None:
    """Test that a connection that lived long resets the backoff."""
    realtime, _, _ = make_realtime(FakeWs([]))
    sleeps: list[float] = []
    clock = iter([0, 100, 200, 300])

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        if len(sleeps) == 2:
            raise asyncio.CancelledError

    with (
        patch.object(realtime, "_run_once", AsyncMock()),
        patch("custom_components.zeromouse.realtime.time.monotonic", lambda: next(clock)),
        patch("custom_components.zeromouse.realtime.asyncio.sleep", fake_sleep),
        pytest.raises(asyncio.CancelledError),
    ):
        await realtime.run()
    assert sleeps == [5, 5]
