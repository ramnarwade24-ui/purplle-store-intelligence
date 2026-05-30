from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from storeintel.api.deps import session_dep
from storeintel.services.anomalies_service import get_active_anomalies


router = APIRouter(tags=["anomalies"])


@router.get("/stores/{store_id}/anomalies")
def store_anomalies(
    store_id: str,
    session: Session = Depends(session_dep),
):
    return get_active_anomalies(session, store_id=store_id)
