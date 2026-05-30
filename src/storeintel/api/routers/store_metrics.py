from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from storeintel.api.deps import session_dep
from storeintel.db.models import Event, Purchase


router = APIRouter(tags=["metrics"])


@router.get("/stores/{store_id}/metrics")
def store_metrics(
    store_id: str,
    session: Session = Depends(session_dep),
):
    # Base visitor set for this store excluding staff
    visitors_subq = (
        select(Event.visitor_id)
        .where(Event.store_id == store_id, Event.is_staff.is_(False))
        .distinct()
        .subquery()
    )

    unique_visitors = session.execute(select(func.count()).select_from(visitors_subq)).scalar_one()

    # Visitors with at least one purchase (scoped to this store's visitor set)
    converted_visitors = session.execute(
        select(func.count(func.distinct(Purchase.visitor_id))).where(Purchase.visitor_id.in_(select(visitors_subq.c.visitor_id)))
    ).scalar_one()

    conversion_rate = float(converted_visitors) / float(unique_visitors) if unique_visitors else 0.0

    # Average dwell time (milliseconds) from events with dwell_ms populated
    avg_dwell_ms = session.execute(
        select(func.avg(Event.dwell_ms)).where(
            Event.store_id == store_id,
            Event.is_staff.is_(False),
            Event.dwell_ms.is_not(None),
        )
    ).scalar_one()
    avg_dwell_time = float(avg_dwell_ms) if avg_dwell_ms is not None else 0.0

    # Queue depth: number of visitors whose latest BILLING_ZONE zone event is zone_enter
    billing_zone = "BILLING_ZONE"
    zone_enter = "zone_enter"
    zone_exit = "zone_exit"

    latest_zone_ts = (
        select(
            Event.visitor_id.label("visitor_id"),
            func.max(Event.timestamp).label("max_ts"),
        )
        .where(
            Event.store_id == store_id,
            Event.is_staff.is_(False),
            Event.zone_id == billing_zone,
            Event.event_type.in_([zone_enter, zone_exit]),
        )
        .group_by(Event.visitor_id)
        .subquery()
    )

    latest_zone_events = (
        select(Event.visitor_id)
        .join(
            latest_zone_ts,
            (Event.visitor_id == latest_zone_ts.c.visitor_id) & (Event.timestamp == latest_zone_ts.c.max_ts),
        )
        .where(
            Event.event_type == zone_enter,
            Event.zone_id == billing_zone,
        )
        .subquery()
    )

    queue_depth = session.execute(select(func.count()).select_from(latest_zone_events)).scalar_one()

    # Abandonment rate: billing-enter visitors without a purchase (scoped)
    billing_visitors_subq = (
        select(Event.visitor_id)
        .where(
            Event.store_id == store_id,
            Event.is_staff.is_(False),
            Event.zone_id == billing_zone,
            Event.event_type == zone_enter,
        )
        .distinct()
        .subquery()
    )

    billing_visitors = session.execute(select(func.count()).select_from(billing_visitors_subq)).scalar_one()

    billing_converted = session.execute(
        select(func.count(func.distinct(Purchase.visitor_id))).where(
            Purchase.visitor_id.in_(select(billing_visitors_subq.c.visitor_id))
        )
    ).scalar_one()

    abandonment_rate = float(billing_visitors - billing_converted) / float(billing_visitors) if billing_visitors else 0.0

    return {
        "unique_visitors": int(unique_visitors),
        "conversion_rate": float(conversion_rate),
        "avg_dwell_time": float(avg_dwell_time),
        "queue_depth": int(queue_depth),
        "abandonment_rate": float(abandonment_rate),
    }
