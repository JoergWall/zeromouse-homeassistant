"""Match ZeroMOUSE events with the passages a cat flap integration reports.

ZeroMOUSE sees a cat at the flap but (without face detection) not which cat it is.
Many cat flaps know the cat from its microchip and report each passage to Home
Assistant. Pairing both by time tells which cat came with or without prey.

A passage source is one Home Assistant entity per cat. Three ways to read passages
from its history are supported:

``attribute``  A timestamp attribute that changes on every passage, optionally with a
               direction attribute. Sure Petcare (core and *sureha*) work like this:
               ``since`` + ``where`` (1 = inside, 2 = outside).
``state``      Every state change is a passage, the new state may tell the direction
               (``on``/``off``, ``home``/``not_home``, …). Fits presence sensors and
               plain contact/vibration sensors mounted on a flap without connectivity.
               With ``time_attribute`` every new value of that attribute is a passage.
``event``      An event entity: its state is the time of the last event and the
               ``event_type`` attribute may tell the direction.

``filter`` limits a source to recorded states whose attributes have given values,
e.g. one cat (RFID) on a flap-wide entity.

Only the Sure Petcare presets were tested with real data. The PetSafe and OnlyCat
presets follow the source code of those integrations.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging
import math
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from .const import CLASSIFICATION_GROUPS, classification_group

_LOGGER = logging.getLogger(__name__)

SOURCE_ATTRIBUTE = "attribute"
SOURCE_STATE = "state"
SOURCE_EVENT = "event"

_IN = ["on", "home", "inside", "in", "entered", "entry", "enter", "inward", "inbound"]
_OUT = ["off", "not_home", "away", "outside", "out", "left", "exit", "exited", "outward"]

PRESETS: dict[str, dict[str, Any]] = {
    # Sure Petcare core integration and sureha: pet presence binary_sensor
    "sureflap": {
        "source": SOURCE_ATTRIBUTE,
        "time_attribute": "since",
        "direction_attribute": "where",
        "in": ["1", "inside"],
        "out": ["2", "outside"],
    },
    # Sure Petcare via surepcha: "since" but no "where", direction from the state
    "sureflap_state": {
        "source": SOURCE_STATE,
        "time_attribute": "since",
        "direction_attribute": None,
        "in": _IN,
        "out": _OUT,
    },
    # PetSafe SmartDoor via petsafe_extended: "<pet> Activity" event entity
    "petsafe": {
        "source": SOURCE_EVENT,
        "time_attribute": "occurred_at",
        "direction_attribute": "event_type",
        "in": ["pet_entered"],
        "out": ["pet_exited"],
    },
    # OnlyCat: flap-wide "Flap event" binary_sensor; add filter: {rfidCode: ...}
    "onlycat": {
        "source": SOURCE_ATTRIBUTE,
        "time_attribute": "timestamp",
        "direction_attribute": "direction",
        "in": ["inward"],
        "out": ["outward"],
    },
    "state": {
        "source": SOURCE_STATE,
        "direction_attribute": None,
        "in": _IN,
        "out": _OUT,
    },
    "event": {
        "source": SOURCE_EVENT,
        "direction_attribute": "event_type",
        "in": [*_IN, "came_in", "pet_entered"],
        "out": [*_OUT, "went_out", "outbound", "pet_exited"],
    },
}
PRESET_NAMES = ["auto", *PRESETS, SOURCE_ATTRIBUTE]

# Direction a flap passage must have to fit a ZeroMOUSE classification group.
# ZeroMOUSE watches cats coming in, "out" is its "leaving detected".
EXPECTED_DIRECTION = {
    "out": "out",
    "prey": "in",
    "clean": "in",
    "undecidable": "in",
    "hand": "in",
}


def _expected_direction(classification: object) -> str | None:
    """Return the direction a passage needs, None for unknown classifications."""
    if not any(classification in group for group in CLASSIFICATION_GROUPS.values()):
        return None
    return EXPECTED_DIRECTION[classification_group(classification)]


DEFAULT_WINDOW_BEFORE = 60
DEFAULT_WINDOW_AFTER = 180

METHOD_FLAP = "flap"
METHOD_ZEROMOUSE = "zeromouse"


@dataclass(frozen=True)
class PassageSource:
    """How passages of one cat are read from one entity."""

    entity_id: str
    name: str
    source: str
    time_attribute: str | None
    direction_attribute: str | None
    in_values: frozenset[str]
    out_values: frozenset[str]
    filters: tuple[tuple[str, frozenset[str]], ...] = ()

    def direction(self, value: Any) -> str | None:
        """Map a raw direction value to "in", "out" or None (unknown)."""
        texts = _texts(value)
        if texts & self.in_values:
            return "in"
        if texts & self.out_values:
            return "out"
        return None

    def accepts(self, attributes: Mapping[str, Any]) -> bool:
        """Return if a recorded state passes the attribute filter."""
        return all(_texts(attributes.get(key)) & values for key, values in self.filters)


@dataclass(frozen=True)
class Passage:
    """One passage of a cat through the flap."""

    source: PassageSource
    time: datetime
    direction: str | None


def _texts(value: Any) -> frozenset[str]:
    """Comparable spellings of a value: live states may hold enums, the recorder
    stores their JSON value (e.g. surepy's Location.INSIDE -> 1)."""
    if value is None:
        return frozenset()
    if isinstance(value, Enum):
        return frozenset({str(value.value).strip().lower(), value.name.strip().lower()})
    return frozenset({str(value).strip().lower()})


def _values(values: Iterable[Any] | str | None) -> frozenset[str]:
    if values is None:
        return frozenset()
    if isinstance(values, str | int | float):
        values = [values]
    return frozenset(text for v in values for text in _texts(v))


def _auto_preset(entity_id: str, state: State | None) -> str:
    attributes = state.attributes if state is not None else {}
    if entity_id.startswith("event."):
        return "petsafe" if "occurred_at" in attributes else "event"
    if "since" in attributes:
        return "sureflap" if "where" in attributes else "sureflap_state"
    if {"eventId", "timestamp", "direction"} <= attributes.keys():
        return "onlycat"
    return "state"


def build_source(config: Mapping[str, Any], state: State | None) -> PassageSource:
    """Create a passage source from a card/service configuration.

    ``preset`` (default ``auto``) fills in the defaults, explicit keys override them.
    """
    entity_id = config["entity"]
    preset = config.get("preset", "auto")
    if preset == "auto":
        preset = _auto_preset(entity_id, state)
    base: dict[str, Any] = dict(PRESETS.get(preset, {"source": SOURCE_ATTRIBUTE}))
    for key in ("source", "time_attribute", "direction_attribute", "in", "out"):
        if key in config:
            base[key] = config[key]
    filters = tuple(
        (str(key), _values(value)) for key, value in (config.get("filter") or {}).items()
    )
    return PassageSource(
        entity_id=entity_id,
        name=str(config.get("name") or entity_id),
        source=base.get("source", SOURCE_STATE),
        time_attribute=base.get("time_attribute"),
        direction_attribute=base.get("direction_attribute"),
        in_values=_values(base.get("in")),
        out_values=_values(base.get("out")),
        filters=filters,
    )


def _from_epoch(number: float) -> datetime | None:
    """Epoch seconds or milliseconds; None for NaN, infinite or out of range."""
    if not math.isfinite(number):
        return None
    try:
        return dt_util.utc_from_timestamp(number / 1000 if number > 1e12 else number)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    """Parse a datetime, an epoch number or text (states are always text)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        parsed: datetime | None = value
    else:
        try:
            return _from_epoch(float(value))
        except (TypeError, ValueError):
            parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    return dt_util.as_utc(parsed) if parsed.tzinfo else parsed.replace(tzinfo=dt_util.UTC)


def passages_from_states(source: PassageSource, states: Sequence[State]) -> list[Passage]:
    """Turn the recorded states of one entity into passages."""
    passages: dict[datetime, Passage] = {}
    for state in states:
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            continue
        attributes = state.attributes
        if not source.accepts(attributes):
            continue
        if source.source == SOURCE_ATTRIBUTE:
            when = _parse_time(attributes.get(source.time_attribute or "since"))
            raw_direction = (
                attributes.get(source.direction_attribute)
                if source.direction_attribute
                else None
            )
        elif source.source == SOURCE_EVENT:
            when = _parse_time(
                attributes.get(source.time_attribute)
                if source.time_attribute
                else state.state
            )
            raw_direction = attributes.get(source.direction_attribute or "event_type")
        else:
            when = (
                _parse_time(attributes.get(source.time_attribute))
                if source.time_attribute
                else dt_util.as_utc(state.last_changed)
            )
            raw_direction = (
                attributes.get(source.direction_attribute)
                if source.direction_attribute
                else state.state
            )
        if when is None or when in passages:
            continue
        passages[when] = Passage(source, when, source.direction(raw_direction))
    return sorted(passages.values(), key=lambda p: p.time)


def match_events(
    events: Sequence[Mapping[str, Any]],
    passages: Sequence[Passage],
    window_before: float = DEFAULT_WINDOW_BEFORE,
    window_after: float = DEFAULT_WINDOW_AFTER,
) -> dict[str, dict[str, Any]]:
    """Pair events with passages, one to one, closest in time first.

    ``events`` need ``event_id``, ``time`` (datetime) and ``classification``; an event
    whose ``cat`` was recognised by ZeroMOUSE itself keeps that cat if no passage fits.
    """
    pairs: list[tuple[float, int, int, float]] = []
    for i, event in enumerate(events):
        when = event.get("time")
        if not isinstance(when, datetime):
            continue
        expected = _expected_direction(event.get("classification"))
        for j, passage in enumerate(passages):
            delta = (passage.time - when).total_seconds()
            if delta < -window_before or delta > window_after:
                continue
            if expected and passage.direction and passage.direction != expected:
                continue
            pairs.append((abs(delta), i, j, delta))
    pairs.sort()

    result: dict[str, dict[str, Any]] = {}
    used_events: set[int] = set()
    used_passages: set[int] = set()
    for _, i, j, delta in pairs:
        if i in used_events or j in used_passages:
            continue
        used_events.add(i)
        used_passages.add(j)
        passage = passages[j]
        result[str(events[i]["event_id"])] = {
            "method": METHOD_FLAP,
            "name": passage.source.name,
            "entity_id": passage.source.entity_id,
            "time": passage.time.isoformat(),
            "delta": round(delta, 1),
            "direction": passage.direction,
        }
    for i, event in enumerate(events):
        if i not in used_events and event.get("cat"):
            result[str(event["event_id"])] = {
                "method": METHOD_ZEROMOUSE,
                "name": event["cat"],
                "entity_id": None,
                "time": None,
                "delta": None,
                "direction": None,
            }
    return result


# Margin around each event for polling delays between a passage and its recording
HISTORY_MARGIN = timedelta(seconds=900)


def time_ranges(
    times: Sequence[datetime], window_before: float, window_after: float
) -> list[tuple[datetime, datetime]]:
    """Merge the history windows around the events into as few ranges as possible."""
    before = timedelta(seconds=window_before) + HISTORY_MARGIN
    after = timedelta(seconds=window_after) + HISTORY_MARGIN
    ranges: list[tuple[datetime, datetime]] = []
    for when in sorted(times):
        start, end = when - before, when + after
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    return ranges


def _read_passages(
    hass: HomeAssistant,
    sources: Sequence[PassageSource],
    ranges: Sequence[tuple[datetime, datetime]],
) -> list[Passage]:
    """Read the recorded states in the given ranges and turn them into passages.

    Runs in the recorder's executor: database access and attribute decoding.
    """
    # Imported lazily: the recorder is an optional (after-)dependency
    from homeassistant.components.recorder import history  # noqa: PLC0415

    entity_ids = sorted({source.entity_id for source in sources})
    recorded: dict[str, list[State]] = {entity_id: [] for entity_id in entity_ids}
    for start, end in ranges:
        states = history.get_significant_states(
            hass,
            start,
            end,
            entity_ids,
            None,
            True,  # include_start_time_state
            False,  # significant_changes_only: we need attribute changes
            False,  # minimal_response
            False,  # no_attributes
        )
        for entity_id, rows in states.items():
            recorded.setdefault(entity_id, []).extend(
                row for row in rows if isinstance(row, State)
            )
    passages: list[Passage] = []
    for source in sources:
        passages.extend(passages_from_states(source, recorded.get(source.entity_id, [])))
    return passages


async def async_correlate(
    hass: HomeAssistant,
    events: Sequence[Mapping[str, Any]],
    configs: Sequence[Mapping[str, Any]],
    window_before: float = DEFAULT_WINDOW_BEFORE,
    window_after: float = DEFAULT_WINDOW_AFTER,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Read flap passages from the recorder and match them with events.

    Only the history around the events is read. Returns the matches and an error
    code if the recorder could not be used.
    """
    sources = [
        build_source(config, hass.states.get(config["entity"])) for config in configs
    ]
    times = [e["time"] for e in events if isinstance(e.get("time"), datetime)]
    passages: list[Passage] = []
    error: str | None = None
    if sources and times:
        if "recorder" not in hass.config.components:
            error = "recorder_not_available"
        else:
            from homeassistant.helpers.recorder import get_instance  # noqa: PLC0415

            passages = await get_instance(hass).async_add_executor_job(
                _read_passages,
                hass,
                sources,
                time_ranges(times, window_before, window_after),
            )
            # The newest passage may not be recorded yet
            for source in sources:
                current = hass.states.get(source.entity_id)
                if current is not None:
                    passages.extend(passages_from_states(source, [current]))
            unique = {(p.source, p.time): p for p in passages}
            passages = sorted(unique.values(), key=lambda p: p.time)
    return match_events(events, passages, window_before, window_after), error
