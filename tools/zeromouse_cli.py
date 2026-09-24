#!/usr/bin/env python3
"""Command line tool to try the reverse engineered ZeroMOUSE API.

Usage:
    pip install aiohttp pycognito
    export ZEROMOUSE_EMAIL=you@example.com     # password is asked interactively
    python tools/zeromouse_cli.py devices
    python tools/zeromouse_cli.py dump            # everything into ./zeromouse_dump.json
    python tools/zeromouse_cli.py image           # newest event image of the first device
    python tools/zeromouse_cli.py watch           # realtime events
    python tools/zeromouse_cli.py set-entry 1     # 0 free, 1 block prey, 2 face detection, 3 locked
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib
import json
import logging
import os
from pathlib import Path
import sys
import types

import aiohttp

# Import the integration's api/realtime modules without Home Assistant.
_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "zeromouse"
_pkg = types.ModuleType("zeromouse")
_pkg.__path__ = [str(_COMPONENT)]
sys.modules["zeromouse"] = _pkg
api_mod = importlib.import_module("zeromouse.api")
realtime_mod = importlib.import_module("zeromouse.realtime")


def _dump(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


async def main(args: argparse.Namespace) -> None:
    email = os.environ.get("ZEROMOUSE_EMAIL") or input("E-Mail: ")
    password = os.environ.get("ZEROMOUSE_PASSWORD") or getpass.getpass("Passwort: ")

    async with aiohttp.ClientSession() as session:
        api = api_mod.ZeroMouseApi(session, email, password)
        await api.async_login()
        print(f"Logged in, ownerID={api.owner_id}", file=sys.stderr)
        devices = await api.async_get_devices()
        device_id = args.device or (devices[0]["deviceID"] if devices else None)

        if args.command == "devices":
            for dev in devices:
                for cat in dev.get("catClusters") or []:
                    cat.pop("embedding", None)
            _dump(devices)
        elif args.command == "shadow":
            _dump(await api.async_get_shadow(device_id))
        elif args.command == "events":
            _dump(await api.async_get_events(device_id, args.limit))
        elif args.command == "stats":
            _dump(await api.async_get_statistics(device_id))
        elif args.command == "user":
            _dump(await api.async_get_user())
        elif args.command == "dump":
            result = {"ownerID": api.owner_id, "user": None, "devices": []}
            try:
                result["user"] = await api.async_get_user()
            except api_mod.ZeroMouseError as err:
                result["user"] = f"ERROR: {err}"
            for dev in devices:
                entry: dict = {"flap": dev}
                for key, call in (
                    ("shadow", api.async_get_shadow(dev["deviceID"])),
                    ("events", api.async_get_events(dev["deviceID"], args.limit)),
                    ("statistics", api.async_get_statistics(dev["deviceID"])),
                ):
                    try:
                        entry[key] = await call
                    except api_mod.ZeroMouseError as err:
                        entry[key] = f"ERROR: {err}"
                for cat in dev.get("catClusters") or []:
                    if cat.get("embedding"):
                        cat["embedding"] = f"<{len(cat['embedding'])} values>"
                result["devices"].append(entry)
            Path(args.out).write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str)
            )
            print(f"Written to {args.out}", file=sys.stderr)
        elif args.command == "image":
            events = await api.async_get_events(device_id, 10)
            for event in events:
                index = api_mod.event_image_index(event)
                if index is None:
                    continue
                data = await api.async_get_event_image(device_id, event["eventID"], index)
                if data:
                    name = f"zeromouse_{event['eventID']}_{index}.jpg"
                    Path(name).write_bytes(data)
                    print(f"{event.get('classification_byNet')}: saved {name}")
                    return
            print("No image found")
        elif args.command == "watch":

            async def on_event(event: dict) -> None:
                _dump(event)

            print("Waiting for events (Ctrl+C to stop)...", file=sys.stderr)
            await realtime_mod.ZeroMouseRealtime(session, api, on_event).run()
        elif args.command == "set-entry":
            _dump(await api.async_set_entry_mode(device_id, int(args.value)))
        elif args.command == "set-undecidable":
            _dump(
                await api.async_update_shadow(
                    device_id, {"system": {"undecidableMode": int(args.value)}}
                )
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "command",
        choices=[
            "devices",
            "shadow",
            "events",
            "stats",
            "user",
            "dump",
            "image",
            "watch",
            "set-entry",
            "set-undecidable",
        ],
    )
    parser.add_argument("value", nargs="?")
    parser.add_argument("--device", help="deviceID (default: first device)")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", default="zeromouse_dump.json")
    parser.add_argument("-v", "--verbose", action="store_true")
    parsed = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if parsed.verbose else logging.WARNING)
    try:
        asyncio.run(main(parsed))
    except KeyboardInterrupt:
        pass
