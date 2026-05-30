from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from storeintel.api.deps import session_dep
from storeintel.core.logging import get_logger
from storeintel.db.models import Event, Store
from storeintel.schemas.events import EventIn


router = APIRouter(tags=["events"])
log = get_logger(__name__)


@router.post("/events")
def ingest_events(
    payload: list[EventIn],
    session: Session = Depends(session_dep),
):
    created = 0

    store_ids = {e.store_id for e in payload}
    if store_ids:
        existing = {
            s.store_id
            for s in session.execute(select(Store).where(Store.store_id.in_(store_ids))).scalars().all()
        }
        for sid in store_ids - existing:
            session.add(Store(store_id=sid))

    for e in payload:
        event_kwargs = {
            "store_id": e.store_id,
            "camera_id": e.camera_id,
            "visitor_id": e.visitor_id,
            "event_type": e.event_type,
            "timestamp": e.timestamp,
            "zone_id": e.zone_id,
            "dwell_ms": e.dwell_ms,
            "is_staff": e.is_staff,
            "confidence": e.confidence,
            "payload": e.metadata,
        }
        if e.event_id is not None:
            event_kwargs["event_id"] = str(e.event_id)
        model = Event(**event_kwargs)
        session.add(model)
        created += 1
    session.commit()
    log.info("events_ingested", count=created)
    return {"inserted": created}


@router.get("/events")
def list_events(
    start: datetime | None = None,
    end: datetime | None = None,
    camera_id: str | None = None,
    limit: int = 200,
    session: Session = Depends(session_dep),
):
    stmt = select(Event).order_by(Event.timestamp.desc()).limit(limit)
    if camera_id:
        stmt = stmt.where(Event.camera_id == camera_id)
    if start:
        stmt = stmt.where(Event.timestamp >= start)
    if end:
        stmt = stmt.where(Event.timestamp <= end)
    rows = session.execute(stmt).scalars().all()
    return jsonable_encoder(
        [
            {
                "event_id": r.event_id,
                "store_id": r.store_id,
                "camera_id": r.camera_id,
                "visitor_id": r.visitor_id,
                "event_type": r.event_type,
                "timestamp": r.timestamp,
                "zone_id": r.zone_id,
                "dwell_ms": r.dwell_ms,
                "is_staff": r.is_staff,
                "confidence": r.confidence,
                "metadata": r.payload,
            }
            for r in rows
        ]
    )
