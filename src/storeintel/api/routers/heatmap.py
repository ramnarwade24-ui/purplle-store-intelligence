from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from storeintel.analytics.heatmap import compute_heatmap_grid
from storeintel.api.deps import session_dep
from storeintel.db.models import Event


router = APIRouter(tags=["heatmap"])


@router.get("/heatmap")
def heatmap(
    width: int = 1920,
    height: int = 1080,
    grid_w: int = 64,
    grid_h: int = 36,
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
    grid = compute_heatmap_grid(events, width=width, height=height, grid_w=grid_w, grid_h=grid_h)
    return {"grid": grid, "grid_w": grid_w, "grid_h": grid_h, "width": width, "height": height}
