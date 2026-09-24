"""AppSync realtime subscription for new ZeroMOUSE events."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import json
import logging
import time
from typing import Any
import uuid

import aiohttp

from .api import SUBSCRIPTION_NEW_EVENT, ZeroMouseApi
from .const import GRAPHQL_HOST, REALTIME_URL

_LOGGER = logging.getLogger(__name__)

# Access tokens live one hour; reconnect with a fresh one before that.
_RECONNECT_AFTER = 45 * 60


class ZeroMouseRealtime:
    """Keeps an AppSync websocket open and reports new events."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api: ZeroMouseApi,
        on_event: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Initialize."""
        self._session = session
        self._api = api
        self._on_event = on_event

    async def run(self) -> None:
        """Run forever, reconnecting with backoff."""
        backoff = 5
        while True:
            started = time.monotonic()
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Realtime connection failed: %r", err)
            if time.monotonic() - started > 60:
                backoff = 5
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 600)

    async def _run_once(self) -> None:
        _, access_token = await self._api.async_get_tokens()
        auth = {"host": GRAPHQL_HOST, "Authorization": access_token}
        header = base64.b64encode(json.dumps(auth).encode()).decode()
        url = f"{REALTIME_URL}?header={header}&payload=e30="

        async with self._session.ws_connect(url, protocols=("graphql-ws",)) as ws:
            await ws.send_json({"type": "connection_init"})
            timeout = 300.0
            sub_id = str(uuid.uuid4())
            deadline = time.monotonic() + _RECONNECT_AFTER

            while time.monotonic() < deadline:
                msg = await ws.receive(timeout=timeout)
                if msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.debug("Realtime socket closed: %s", msg)
                    return
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                kind = data.get("type")

                if kind == "connection_ack":
                    timeout_ms = (data.get("payload") or {}).get("connectionTimeoutMs")
                    if timeout_ms:
                        timeout = timeout_ms / 1000
                    await ws.send_json(
                        {
                            "id": sub_id,
                            "type": "start",
                            "payload": {
                                "data": json.dumps(
                                    {"query": SUBSCRIPTION_NEW_EVENT, "variables": {}}
                                ),
                                "extensions": {"authorization": auth},
                            },
                        }
                    )
                elif kind == "start_ack":
                    _LOGGER.debug("Realtime subscription active")
                elif kind == "data":
                    event = (
                        (data.get("payload") or {}).get("data") or {}
                    ).get("onCreateMbrPtfEventData")
                    if event:
                        await self._on_event(event)
                elif kind in ("error", "connection_error"):
                    _LOGGER.debug("Realtime error: %s", data)
                    return
                # "ka" keep-alive needs no answer

            await ws.send_json({"id": sub_id, "type": "stop"})
