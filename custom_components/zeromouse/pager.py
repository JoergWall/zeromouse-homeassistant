"""Filtered, unlimited paging through ZeroMOUSE events of one or more devices.

The cloud returns events per device in pages of up to 100, newest first. A pager
keeps one stream per device, filters the events and merges the streams by time, so
"load more" in the dashboard continues exactly where the previous page ended, even
across several devices.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import secrets
import time
from typing import Any

from .api import ZeroMouseApi, parse_event_time
from .const import CLASSIFICATION_GROUPS

# Check boxes of the app's filter dialog ("Keine Beute erkannt", "Beute erkannt", ...)
FILTER_GROUPS = CLASSIFICATION_GROUPS
# Checked by default in the app; "out" only with hidden events enabled
DEFAULT_GROUPS = ("clean", "prey", "undecidable", "hand")
# The app's unfiltered list shows these although the device marks them hidden
_SHOWN_WHEN_HIDDEN = frozenset({"early", "late", "undecidable"})

PAGE_SIZE = 100
# Upper bound of cloud requests for one page of results (rare filters)
MAX_REQUESTS_PER_CALL = 20
MAX_PAGERS = 64
MAX_PAGERS_PER_USER = 16
PAGER_TTL = 3600  # seconds

_OLDEST = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class EventFilter:
    """Which events a pager returns."""

    groups: frozenset[str] = frozenset()
    favorites_only: bool = False
    include_hidden: bool = False
    since: datetime | None = None

    def matches(self, event: dict[str, Any]) -> bool:
        """Return if the event passes the filter."""
        if event.get("isDeleted"):
            return False
        if self.favorites_only:
            # Like the app: favourites regardless of the other filters
            return bool(event.get("isFavorite"))
        classification = event.get("classification_byNet")
        if self.groups:
            # Like the app: the check boxes decide, hidden or not
            return any(
                classification in FILTER_GROUPS.get(group, frozenset({group}))
                for group in self.groups
            )
        if self.include_hidden:
            return True
        # The app's list without filter
        if classification in _SHOWN_WHEN_HIDDEN:
            return True
        return not event.get("isHidden") and classification != "free"


@dataclass
class DeviceStream:
    """Events of one device, fetched page by page."""

    entry_id: str
    device_id: str
    api: ZeroMouseApi
    event_filter: EventFilter
    token: str | None = None
    exhausted: bool = False
    buffer: deque[tuple[datetime, dict[str, Any]]] = field(default_factory=deque)

    async def async_fetch(self) -> None:
        """Fetch the next page into the buffer."""
        items, self.token = await self.api.async_get_events_page(
            self.device_id,
            self.token,
            PAGE_SIZE,
            favorites=self.event_filter.favorites_only,
        )
        since = self.event_filter.since
        for event in items:
            when = parse_event_time(event) or _OLDEST
            if since is not None and when < since:
                self.exhausted = True
                break
            if self.event_filter.matches(event):
                self.buffer.append((when, event))
        if not self.token:
            self.exhausted = True


class EventPager:
    """Merges the device streams into one list, newest first."""

    def __init__(self, streams: Iterable[DeviceStream], user_id: str | None) -> None:
        """Initialize."""
        self.streams = list(streams)
        self.user_id = user_id
        self.touched = time.monotonic()

    @property
    def has_more(self) -> bool:
        """Return if more events can be loaded."""
        return any(s.buffer or not s.exhausted for s in self.streams)

    async def async_next(
        self, limit: int
    ) -> list[tuple[DeviceStream, dict[str, Any]]]:
        """Return up to ``limit`` further events.

        Fewer events are returned (with ``has_more`` still true) if a rare filter
        needed more than ``MAX_REQUESTS_PER_CALL`` cloud requests.
        """
        self.touched = time.monotonic()
        taken: list[tuple[DeviceStream, tuple[datetime, dict[str, Any]]]] = []
        requests = 0
        try:
            while len(taken) < limit:
                for stream in self.streams:
                    while (
                        not stream.buffer
                        and not stream.exhausted
                        and requests < MAX_REQUESTS_PER_CALL
                    ):
                        await stream.async_fetch()
                        requests += 1
                if any(not s.buffer and not s.exhausted for s in self.streams):
                    # A stream could still hold newer events: stop instead of
                    # returning events out of order.
                    break
                candidates = [s for s in self.streams if s.buffer]
                if not candidates:
                    break
                newest = max(candidates, key=lambda s: s.buffer[0][0])
                taken.append((newest, newest.buffer.popleft()))
        except BaseException:
            # Nothing is lost: the next call returns the same events again
            for stream, item in reversed(taken):
                stream.buffer.appendleft(item)
            raise
        return [(stream, item[1]) for stream, item in taken]

    def give_back(self, page: list[tuple[DeviceStream, dict[str, Any]]]) -> None:
        """Put a page back if it could not be delivered."""
        for stream, event in reversed(page):
            stream.buffer.appendleft((parse_event_time(event) or _OLDEST, event))


class PagerStore:
    """Keeps open pagers between "load more" calls."""

    def __init__(self) -> None:
        """Initialize."""
        self._pagers: OrderedDict[str, EventPager] = OrderedDict()

    def _expire(self) -> None:
        now = time.monotonic()
        for cursor in [c for c, p in self._pagers.items() if now - p.touched > PAGER_TTL]:
            del self._pagers[cursor]
        while len(self._pagers) > MAX_PAGERS:
            self._pagers.popitem(last=False)

    def add(self, pager: EventPager) -> str:
        """Store a pager and return its cursor.

        Each user keeps at most ``MAX_PAGERS_PER_USER`` lists, so one user cannot
        push out the lists of others.
        """
        own = [c for c, p in self._pagers.items() if p.user_id == pager.user_id]
        for cursor in own[: max(0, len(own) - MAX_PAGERS_PER_USER + 1)]:
            del self._pagers[cursor]
        cursor = secrets.token_urlsafe(16)
        self._pagers[cursor] = pager
        self._expire()
        return cursor

    def get(self, cursor: str, user_id: str | None) -> EventPager | None:
        """Return the pager of a cursor if it belongs to the user."""
        self._expire()
        pager = self._pagers.get(cursor)
        if pager is None or pager.user_id != user_id:
            return None
        self._pagers.move_to_end(cursor)
        return pager

    def remove(self, cursor: str) -> None:
        """Forget a finished pager."""
        self._pagers.pop(cursor, None)

    def release(self, cursor: str, user_id: str | None) -> None:
        """Forget a pager its user no longer needs."""
        pager = self._pagers.get(cursor)
        if pager is not None and pager.user_id == user_id:
            del self._pagers[cursor]
