from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from storeintel.analytics.funnel import compute_funnel
from storeintel.api.deps import session_dep
from storeintel.db.models import Event


router = APIRouter(tags=["funnel"])


@router.get("/funnel")
def funnel(
    steps: list[str] = Query(default=["enter", "exit"]),
    start: datetime | None = None,
    end: datetime | None = None,
    camera_id: str | None = None,
    session: Session = Depends(session_dep),
):
    stmt = select(Event)
    if camera_id:
        stmt = stmt.where(Event.camera_id == camera_id)
    if start:
        stmt = stmt.where(Event.timestamp >= start)
    if end:
        stmt = stmt.where(Event.timestamp <= end)
    events = session.execute(stmt).scalars().all()
    result = compute_funnel(events, steps=steps)
    return [r.__dict__ for r in result]
