from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from storeintel.analytics.anomaly import detect_count_anomalies
from storeintel.api.deps import session_dep
from storeintel.db.models import Event


router = APIRouter(tags=["anomalies"])


@router.get("/anomalies")
def anomalies(
    event_name: str = "enter",
    bucket_seconds: int = 3600,
    z_threshold: float = 3.0,
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
    ts = [e.timestamp for e in events if e.event_type == event_name]
    result = detect_count_anomalies(ts, bucket_seconds=bucket_seconds, z_threshold=z_threshold)
    return [
        {"bucket_start": a.bucket_start.isoformat(), "count": a.count, "zscore": a.zscore}
        for a in result
    ]
