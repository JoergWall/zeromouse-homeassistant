"""Tests for matching events with cat flap passages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.zeromouse.correlation import (
    PassageSource,
    async_correlate,
    build_source,
    match_events,
    passages_from_states,
)
from homeassistant.components.recorder import Recorder
from homeassistant.core import HomeAssistant, State

T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """Override: these tests need no integration, and the recorder must start first."""


def _state(entity_id: str, state: str, changed: datetime, **attrs: Any) -> State:
    return State(entity_id, state, attrs, last_changed=changed, last_updated=changed)


def _event(event_id: str, when: datetime, cls: str = "clean", cat: str | None = None) -> dict:
    return {"event_id": event_id, "time": when, "classification": cls, "cat": cat}


def test_presets() -> None:
    """Test automatic preset detection and overrides."""
    sure = build_source(
        {"entity": "binary_sensor.tiger", "name": "Tiger"},
        _state("binary_sensor.tiger", "on", T0, since="x", where=1),
    )
    assert (sure.source, sure.time_attribute, sure.direction_attribute) == (
        "attribute",
        "since",
        "where",
    )
    assert sure.direction(1) == "in" and sure.direction("2") == "out"

    contact = build_source({"entity": "binary_sensor.flap_contact"}, None)
    assert contact.source == "state"
    assert contact.name == "binary_sensor.flap_contact"
    assert contact.direction("on") == "in"

    event = build_source({"entity": "event.luna_flap"}, None)
    assert event.source == "event"
    assert event.direction("Entry") == "in" and event.direction("exit") == "out"

    custom = build_source(
        {
            "entity": "sensor.flap",
            "preset": "attribute",
            "time_attribute": "last_passage",
            "direction_attribute": "dir",
            "in": ["IN"],
            "out": ["OUT"],
        },
        None,
    )
    assert custom.time_attribute == "last_passage"
    assert custom.direction("in") == "in" and custom.direction("x") is None
    assert custom.direction(None) is None

    overridden = build_source({"entity": "binary_sensor.x", "preset": "sureflap", "out": ["3"]}, None)
    assert overridden.direction("3") == "out" and overridden.direction("2") is None


def test_passages_attribute_source() -> None:
    """Test SureFlap style passages: one per new `since` value."""
    source = build_source({"entity": "binary_sensor.tiger", "preset": "sureflap"}, None)
    states = [
        _state("binary_sensor.tiger", "on", T0, since=(T0 - timedelta(hours=1)).isoformat(), where=1),
        # attribute-only change with the same since: no new passage
        _state("binary_sensor.tiger", "on", T0, since=(T0 - timedelta(hours=1)).isoformat(), where=1, x=1),
        _state("binary_sensor.tiger", "on", T0, since=(T0 + timedelta(seconds=14)).isoformat(), where=1),
        _state("binary_sensor.tiger", "off", T0, since=(T0 + timedelta(hours=2)).isoformat(), where=2),
        _state("binary_sensor.tiger", "unavailable", T0),
        _state("binary_sensor.tiger", "on", T0, since="garbage", where=1),
        _state("binary_sensor.tiger", "on", T0),
    ]
    passages = passages_from_states(source, states)
    assert [(p.time - T0).total_seconds() for p in passages] == [-3600, 14, 7200]
    assert [p.direction for p in passages] == ["in", "in", "out"]


def test_passages_state_and_event_sources() -> None:
    """Test state change and event entity sources."""
    contact = build_source({"entity": "binary_sensor.flap"}, None)
    states = [
        _state("binary_sensor.flap", "off", T0),
        _state("binary_sensor.flap", "on", T0 + timedelta(seconds=10), battery=90),
        _state("binary_sensor.flap", "on", T0 + timedelta(seconds=10), battery=89),
    ]
    passages = passages_from_states(contact, states)
    assert [p.direction for p in passages] == ["out", "in"]

    event = build_source({"entity": "event.flap"}, None)
    passages = passages_from_states(
        event,
        [
            _state("event.flap", (T0 + timedelta(seconds=5)).isoformat(), T0, event_type="entry"),
            _state("event.flap", "unknown", T0),
            _state("event.flap", 1792500000, T0, event_type="exit"),
        ],
    )
    assert [p.direction for p in passages] == ["in", "out"]

    timed = build_source(
        {"entity": "sensor.flap", "preset": "state", "time_attribute": "at"}, None
    )
    passages = passages_from_states(
        timed, [_state("sensor.flap", "home", T0, at=1792500000000)]
    )
    assert passages[0].time.year == 2026


def test_match_events() -> None:
    """Test one-to-one matching, direction and window."""
    tiger = build_source({"entity": "binary_sensor.tiger", "name": "Tiger", "preset": "sureflap"}, None)
    luna = build_source({"entity": "binary_sensor.luna", "name": "Luna", "preset": "sureflap"}, None)
    passages = passages_from_states(
        tiger,
        [_state("binary_sensor.tiger", "on", T0, since=(T0 + timedelta(seconds=12)).isoformat(), where=1)],
    ) + passages_from_states(
        luna,
        [
            _state("binary_sensor.luna", "on", T0, since=(T0 + timedelta(seconds=20)).isoformat(), where=1),
            _state("binary_sensor.luna", "off", T0, since=(T0 + timedelta(seconds=500)).isoformat(), where=2),
        ],
    )
    events = [
        _event("a", T0),  # Tiger +12 s (Luna +20 s goes to b)
        _event("b", T0 + timedelta(seconds=18)),  # Luna +2 s is the closest pair
        _event("c", T0 + timedelta(seconds=490), "out"),  # Luna went out +10 s
        _event("d", T0 + timedelta(seconds=495), "prey", cat="Mia"),  # no passage, ZeroMOUSE cat
        _event("e", T0 + timedelta(hours=5)),  # nothing in the window
        {"event_id": "f", "time": None, "classification": "clean"},
    ]
    result = match_events(events, passages)
    assert result["a"]["name"] == "Tiger" and result["a"]["delta"] == 12
    assert result["b"]["name"] == "Luna" and result["b"]["delta"] == 2
    assert result["c"]["direction"] == "out"
    assert result["d"] == {
        "method": "zeromouse",
        "name": "Mia",
        "entity_id": None,
        "time": None,
        "delta": None,
        "direction": None,
    }
    assert "e" not in result and "f" not in result


def test_direction_must_fit() -> None:
    """Test that an entry is not matched with a passage going out."""
    source = PassageSource("x.y", "Y", "attribute", "since", "where", frozenset({"1"}), frozenset({"2"}))
    passages = passages_from_states(
        source, [_state("x.y", "on", T0, since=(T0 + timedelta(seconds=5)).isoformat(), where=2)]
    )
    assert match_events([_event("a", T0, "clean")], passages) == {}
    # Grouped like the app: "early" is a clean entry
    assert match_events([_event("a", T0, "early")], passages) == {}
    # Unknown classifications accept any direction
    assert "a" in match_events([_event("a", T0, "free")], passages)


async def test_async_correlate_without_recorder(hass: HomeAssistant) -> None:
    """Test the error when the recorder is not loaded."""
    matches, error = await async_correlate(
        hass, [_event("a", T0)], [{"entity": "binary_sensor.tiger"}]
    )
    assert error == "recorder_not_available"
    assert matches == {}
    # Nothing to do without sources or events
    assert await async_correlate(hass, [], []) == ({}, None)


async def test_async_correlate_with_recorder(
    recorder_mock: Recorder, hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test reading SureFlap passages from the recorder history."""
    freezer.move_to(T0)
    hass.states.async_set(
        "binary_sensor.tiger", "on", {"since": (T0 - timedelta(days=1)).isoformat(), "where": 1}
    )
    await async_wait_recording_done(hass)
    freezer.move_to(T0 + timedelta(seconds=20))
    hass.states.async_set(
        "binary_sensor.tiger", "on", {"since": (T0 + timedelta(seconds=14)).isoformat(), "where": 1}
    )
    await async_wait_recording_done(hass)
    freezer.move_to(T0 + timedelta(minutes=5))

    matches, error = await async_correlate(
        hass,
        [_event("a", T0), _event("b", T0 - timedelta(hours=3))],
        [{"entity": "binary_sensor.tiger", "name": "Tiger"}],
    )
    assert error is None
    assert matches == {
        "a": {
            "method": "flap",
            "name": "Tiger",
            "entity_id": "binary_sensor.tiger",
            "time": (T0 + timedelta(seconds=14)).isoformat(),
            "delta": 14.0,
            "direction": "in",
        }
    }


@pytest.mark.parametrize("value", [None, "nope"])
def test_parse_time_invalid(value: Any) -> None:
    """Test that unparsable time attributes are skipped."""
    source = build_source({"entity": "binary_sensor.t", "preset": "sureflap"}, None)
    assert passages_from_states(source, [_state("binary_sensor.t", "on", T0, since=value)]) == []


def test_live_enum_direction() -> None:
    """Test that enum values of live states (surepy Location) are understood."""
    from enum import IntEnum

    class Location(IntEnum):
        INSIDE = 1
        OUTSIDE = 2

    source = build_source({"entity": "binary_sensor.t", "preset": "sureflap"}, None)
    assert source.direction(Location.INSIDE) == "in"
    assert source.direction(Location.OUTSIDE) == "out"
    assert source.direction("inside") == "in"


def test_more_presets() -> None:
    """Test surepcha, PetSafe and OnlyCat presets (from their source code)."""
    surepcha = build_source(
        {"entity": "binary_sensor.tiger_presence"},
        _state("binary_sensor.tiger_presence", "on", T0, since="x", tag_id=1),
    )
    assert (surepcha.source, surepcha.time_attribute) == ("state", "since")
    passages = passages_from_states(
        surepcha,
        [
            _state("binary_sensor.tiger_presence", "on", T0, since=(T0 - timedelta(hours=1)).isoformat()),
            _state("binary_sensor.tiger_presence", "on", T0, since=(T0 + timedelta(seconds=9)).isoformat()),
        ],
    )
    assert [(p.time - T0).total_seconds() for p in passages] == [-3600, 9]
    assert {p.direction for p in passages} == {"in"}

    petsafe = build_source(
        {"entity": "event.tiger_activity"},
        _state("event.tiger_activity", T0.isoformat(), T0, occurred_at="x", event_type="pet_entered"),
    )
    assert (petsafe.source, petsafe.time_attribute) == ("event", "occurred_at")
    passages = passages_from_states(
        petsafe,
        [
            _state(
                "event.tiger_activity",
                (T0 + timedelta(seconds=40)).isoformat(),
                T0,
                occurred_at=(T0 + timedelta(seconds=8)).isoformat(),
                event_type="pet_entered",
            )
        ],
    )
    assert passages[0].direction == "in"
    assert (passages[0].time - T0).total_seconds() == 8

    onlycat_attrs = {"eventId": 1, "timestamp": "x", "direction": "INWARD"}
    auto = build_source(
        {"entity": "binary_sensor.oc_1_event"},
        _state("binary_sensor.oc_1_event", "on", T0, **onlycat_attrs),
    )
    assert auto.time_attribute == "timestamp"
    luna = build_source(
        {
            "entity": "binary_sensor.oc_1_event",
            "name": "Luna",
            "preset": "onlycat",
            "filter": {"rfidCode": "900111", "action": ["TRANSIT", "BREACH"]},
        },
        None,
    )
    rows = [
        _state("binary_sensor.oc_1_event", "on", T0, eventId=1, timestamp=(T0 + timedelta(seconds=3)).isoformat(),
               rfidCode="900111", direction="INWARD", action="TRANSIT"),
        _state("binary_sensor.oc_1_event", "off", T0, eventId=1, timestamp=(T0 + timedelta(seconds=3)).isoformat()),
        _state("binary_sensor.oc_1_event", "on", T0, eventId=2, timestamp=(T0 + timedelta(seconds=60)).isoformat(),
               rfidCode="900222", direction="INWARD", action="TRANSIT"),
        _state("binary_sensor.oc_1_event", "on", T0, eventId=3, timestamp=(T0 + timedelta(seconds=90)).isoformat(),
               rfidCode="900111", direction="OUTWARD", action="PEEK"),
    ]
    passages = passages_from_states(luna, rows)
    assert len(passages) == 1
    assert passages[0].direction == "in"
    assert (passages[0].time - T0).total_seconds() == 3



@pytest.mark.parametrize("value", ["nan", "inf", 1e300, True])
def test_parse_time_rejects_bad_numbers(value: Any) -> None:
    """Test that NaN, infinite or huge numbers do not raise."""
    source = build_source({"entity": "binary_sensor.t", "preset": "sureflap"}, None)
    assert passages_from_states(source, [_state("binary_sensor.t", "on", T0, since=value)]) == []


def test_time_ranges() -> None:
    """Test that the history is read only around the events."""
    from custom_components.zeromouse.correlation import HISTORY_MARGIN, time_ranges

    events = [T0, T0 + timedelta(minutes=5), T0 + timedelta(days=30)]
    ranges = time_ranges(events, 60, 180)
    assert len(ranges) == 2
    assert ranges[0][0] == T0 - timedelta(seconds=60) - HISTORY_MARGIN
    assert ranges[0][1] == T0 + timedelta(minutes=5, seconds=180) + HISTORY_MARGIN
    assert ranges[1][0] == T0 + timedelta(days=30, seconds=-60) - HISTORY_MARGIN
