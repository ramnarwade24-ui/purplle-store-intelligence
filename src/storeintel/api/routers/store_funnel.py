from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from storeintel.api.deps import session_dep
from storeintel.db.models import Event, Purchase


router = APIRouter(tags=["funnel"])


@dataclass
class _Session:
    visitor_id: str
    entry_time: datetime
    exit_time: datetime | None
    last_event_time: datetime
    zone_visit: bool = False
    billing: bool = False
    purchase: bool = False


_ENTRY_TYPES = {"enter", "entry"}
_EXIT_TYPES = {"exit"}
_ZONE_TYPES = {"zone_enter", "zone_exit", "zone_dwell"}
_BILLING_ZONE = "BILLING_ZONE"


def _build_sessions(events: list[Event]) -> list[_Session]:
    """Build visitor sessions based on ENTRY/EXIT events.

    - Session starts on an entry event.
    - Session ends on an exit event.
    - Re-entry handling: if an entry occurs while a session is open, the previous
      session is closed at the new entry timestamp and a new session begins.
    - No double counting: stage flags are booleans per session.
    """

    sessions: list[_Session] = []
    open_by_visitor: dict[str, _Session] = {}

    for e in events:
        vid = e.visitor_id
        et = e.event_type
        ts = e.timestamp

        current = open_by_visitor.get(vid)
        if current is not None:
            current.last_event_time = max(current.last_event_time, ts)

        if et in _ENTRY_TYPES:
            if current is not None:
                # close previous session at re-entry time
                current.exit_time = ts
                sessions.append(current)
            new_sess = _Session(visitor_id=vid, entry_time=ts, exit_time=None, last_event_time=ts)
            open_by_visitor[vid] = new_sess
            continue

        if current is None:
            # ignore non-entry events outside a session
            continue

        # stage flags inside session
        if e.zone_id is not None and et in _ZONE_TYPES:
            current.zone_visit = True
        if et == "zone_enter" and e.zone_id == _BILLING_ZONE:
            current.billing = True

        if et in _EXIT_TYPES:
            current.exit_time = ts
            sessions.append(current)
            del open_by_visitor[vid]

    # close any remaining sessions at their last seen timestamp
    for sess in open_by_visitor.values():
        sess.exit_time = sess.last_event_time
        sessions.append(sess)

    return sessions


def _dropoff(prev: int, curr: int) -> float:
    return float(prev - curr) / float(prev) * 100.0 if prev else 0.0


@router.get("/stores/{store_id}/funnel")
def store_funnel(
    store_id: str,
    session: Session = Depends(session_dep),
):
    # Load events for store, excluding staff, in chronological order.
    events = (
        session.execute(
            select(Event)
            .where(Event.store_id == store_id, Event.is_staff.is_(False))
            .order_by(Event.visitor_id.asc(), Event.timestamp.asc())
        )
        .scalars()
        .all()
    )

    sessions = _build_sessions(events)

    # Attach purchase stage: any purchase for visitor within session window.
    if sessions:
        visitor_ids = sorted({s.visitor_id for s in sessions})
        min_ts = min(s.entry_time for s in sessions)
        max_ts = max((s.exit_time or s.last_event_time) for s in sessions)

        purchases = (
            session.execute(
                select(Purchase).where(
                    Purchase.visitor_id.in_(visitor_ids),
                    Purchase.purchase_timestamp >= min_ts,
                    Purchase.purchase_timestamp <= max_ts,
                )
            )
            .scalars()
            .all()
        )

        by_visitor: dict[str, list[datetime]] = {}
        for p in purchases:
            by_visitor.setdefault(p.visitor_id, []).append(p.purchase_timestamp)
        for v in by_visitor.values():
            v.sort()

        for s in sessions:
            pts = by_visitor.get(s.visitor_id)
            if not pts:
                continue
            start = s.entry_time
            end = s.exit_time or s.last_event_time
            # any purchase within the session window
            s.purchase = any(start <= t <= end for t in pts)

    entry_count = len(sessions)
    zone_visit_count = sum(1 for s in sessions if s.zone_visit)
    billing_count = sum(1 for s in sessions if s.billing)
    purchase_count = sum(1 for s in sessions if s.purchase)

    stages = [
        {"stage": "ENTRY", "count": entry_count, "dropoff_pct": 0.0},
        {"stage": "ZONE_VISIT", "count": zone_visit_count, "dropoff_pct": _dropoff(entry_count, zone_visit_count)},
        {"stage": "BILLING", "count": billing_count, "dropoff_pct": _dropoff(zone_visit_count, billing_count)},
        {"stage": "PURCHASE", "count": purchase_count, "dropoff_pct": _dropoff(billing_count, purchase_count)},
    ]

    return {"sessions": entry_count, "stages": stages}
