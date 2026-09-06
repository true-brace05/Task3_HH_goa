"""Simple event bus for Phase 1.

Thin wrapper around evidence.timeline.TimelineCollector so imports
can be `from utils.events import EventBus` as specified.
Keeps evidence module independent from search.
"""

from evidence.timeline import TimelineCollector, create_timeline_event
from evidence.schema import TimelineEvent

EventBus = TimelineCollector

__all__ = ["EventBus", "TimelineCollector", "create_timeline_event", "TimelineEvent"]
