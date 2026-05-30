from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storeintel.api.deps import session_dep
from storeintel.core.logging import get_logger
from storeintel.db.models import Event, Store
from storeintel.schemas.events import EventIn


router = APIRouter(tags=["events"])
log = get_logger(__name__)

MAX_BATCH_SIZE = 500


@router.post("/events/ingest")
def ingest_events(
    payload: list[Any] = Body(...),
    session: Session = Depends(session_dep),
):
    """Ingest a batch of events with partial success support.

    Requirements implemented:
    - Accept batch of events
    - Validate schema (per-item)
    - Deduplicate by event_id (within-batch + existing rows)
    - Store in SQLite
    - Partial success (bad rows don't reject whole batch)
    - Maximum batch size 500

    Returns counts: {accepted, duplicates, failed}
    """

    if len(payload) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=413, detail=f"Maximum batch size is {MAX_BATCH_SIZE}")

    accepted = 0
    duplicates = 0
    failed = 0

    validated: list[EventIn] = []
    for item in payload:
        try:
            validated.append(EventIn.model_validate(item))
        except ValidationError:
            failed += 1

    # Deduplicate within batch on event_id (when provided)
    seen_ids: set[str] = set()
    candidates: list[EventIn] = []
    candidate_ids: list[str] = []

    for ev in validated:
        if ev.event_id is None:
            candidates.append(ev)
            continue

        eid = str(ev.event_id)
        if eid in seen_ids:
            duplicates += 1
            continue
        seen_ids.add(eid)
        candidates.append(ev)
        candidate_ids.append(eid)

    # Deduplicate against DB on event_id
    existing_ids: set[str] = set()
    if candidate_ids:
        rows = session.execute(select(Event.event_id).where(Event.event_id.in_(candidate_ids))).scalars().all()
        existing_ids = set(rows)

    final_events: list[EventIn] = []
    for ev in candidates:
        if ev.event_id is not None and str(ev.event_id) in existing_ids:
            duplicates += 1
            continue
        final_events.append(ev)

    # Ensure stores exist for FK constraint
    store_ids = {e.store_id for e in final_events}
    if store_ids:
        existing = {
            s.store_id
            for s in session.execute(select(Store).where(Store.store_id.in_(store_ids))).scalars().all()
        }
        for sid in store_ids - existing:
            session.add(Store(store_id=sid))

    # Insert with savepoints to allow partial success on DB constraint errors.
    # Note: SQLAlchemy implicitly begins a transaction on first DB use (e.g., SELECT),
    # so we avoid calling session.begin() here.
    for e in final_events:
        event_kwargs: dict[str, Any] = {
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

        try:
            with session.begin_nested():
                session.add(Event(**event_kwargs))
                session.flush()
                accepted += 1
        except IntegrityError:
            duplicates += 1
        except Exception:
            failed += 1

    session.commit()

    log.info("events_ingest_complete", accepted=accepted, duplicates=duplicates, failed=failed)
    return {"accepted": accepted, "duplicates": duplicates, "failed": failed}
