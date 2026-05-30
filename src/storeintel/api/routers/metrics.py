from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from storeintel.analytics.metrics import compute_visitor_counts
from storeintel.api.deps import session_dep
from storeintel.db.models import Event


router = APIRouter(tags=["metrics"])


def _query_events(
    session: Session,
    *,
    start: datetime | None,
    end: datetime | None,
    camera_id: str | None,
):
    stmt = select(Event)
    if camera_id:
        stmt = stmt.where(Event.camera_id == camera_id)
    if start:
        stmt = stmt.where(Event.timestamp >= start)
    if end:
        stmt = stmt.where(Event.timestamp <= end)
    return session.execute(stmt).scalars().all()


@router.get("/metrics/visitors")
def visitors(
    start: datetime | None = None,
    end: datetime | None = None,
    camera_id: str | None = None,
    session: Session = Depends(session_dep),
):
    events = _query_events(session, start=start, end=end, camera_id=camera_id)
    counts = compute_visitor_counts(events)
    return counts.__dict__

