from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from storeintel.db.models import Event


@dataclass(frozen=True)
class VisitorCounts:
    total_events: int
    unique_visitors: int
    enters: int
    exits: int


def compute_visitor_counts(events: Iterable[Event]) -> VisitorCounts:
    events_list = list(events)
    unique = {e.visitor_id for e in events_list if e.visitor_id is not None}
    enters = sum(1 for e in events_list if e.event_type == "enter")
    exits = sum(1 for e in events_list if e.event_type == "exit")
    return VisitorCounts(
        total_events=len(events_list),
        unique_visitors=len(unique),
        enters=enters,
        exits=exits,
    )


def filter_events(
    events: Iterable[Event],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    camera_id: str | None = None,
) -> list[Event]:
    out: list[Event] = []
    for e in events:
        if start and e.timestamp < start:
            continue
        if end and e.timestamp > end:
            continue
        if camera_id and e.camera_id != camera_id:
            continue
        out.append(e)
    return out
