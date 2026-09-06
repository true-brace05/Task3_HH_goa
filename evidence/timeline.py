"""Event timeline for evidence (Phase 1: in-memory collector)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from evidence.schema import TimelineEvent


ALLOWED_EVENTS = {
    "discovery_complete",
    "normalization_complete",
    "acquisition_complete",
    "evidence_built",
    "blockchain_registered",
    "verification_complete",
}


def create_timeline_event(event: str, detail: dict | None = None, actor: str = "system", ts: str | None = None) -> TimelineEvent:
    """Create a TimelineEvent with current UTC timestamp if not provided."""
    if event not in ALLOWED_EVENTS:
        raise ValueError(f"event must be one of {ALLOWED_EVENTS}, got: {event!r}")
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    if detail is None:
        detail = {}
    if not isinstance(detail, dict):
        raise ValueError("detail must be dict")
    return TimelineEvent(ts=ts, event=event, detail=detail, actor=actor)


class TimelineCollector:
    """Simple in-memory timeline collector.

    Supports emit(event) and get_timeline() as required by spec.
    Designed to be additive — Member-2 code does NOT need to emit events yet.
    """

    def __init__(self):
        self._events: List[TimelineEvent] = []

    def emit(self, event: TimelineEvent | dict) -> None:
        if isinstance(event, dict):
            event = TimelineEvent.from_dict(event)
        if not isinstance(event, TimelineEvent):
            raise TypeError(f"emit expects TimelineEvent or dict, got {type(event).__name__}")
        self._events.append(event)

    def emit_event(self, event: str, detail: dict | None = None, actor: str = "system", ts: str | None = None) -> TimelineEvent:
        ev = create_timeline_event(event, detail=detail, actor=actor, ts=ts)
        self.emit(ev)
        return ev

    def get_timeline(self) -> List[TimelineEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
