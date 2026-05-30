from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from storeintel.api.deps import session_dep
from storeintel.db.models import Event


router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/health")
def health(session: Session = Depends(session_dep)):
    service_status = "ok"
    database_status = "ok"
    last_event_timestamp: str | None = None
    stale_feed_warning = True

    try:
        last_ts = session.execute(select(func.max(Event.timestamp))).scalar_one()
        if last_ts is not None:
            if last_ts.tzinfo is None or last_ts.tzinfo.utcoffset(last_ts) is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            last_event_timestamp = last_ts.isoformat()
            stale_feed_warning = (now - last_ts) > timedelta(minutes=10)
    except Exception:
        service_status = "degraded"
        database_status = "error"
        last_event_timestamp = None
        stale_feed_warning = True

    return {
        "service_status": service_status,
        "database_status": database_status,
        "last_event_timestamp": last_event_timestamp,
        "stale_feed_warning": stale_feed_warning,
    }
