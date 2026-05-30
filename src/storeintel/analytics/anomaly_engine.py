from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from storeintel.db.models import Event, Purchase
from storeintel.video.zone_manager import (
    BILLING_ZONE,
    BOTTOM_BRANDS_ZONE,
    ENTRY_ZONE,
    FOH_ZONE,
    TOP_BRANDS_ZONE,
)


QUEUE_SPIKE = "QUEUE_SPIKE"
CONVERSION_DROP = "CONVERSION_DROP"
DEAD_ZONE = "DEAD_ZONE"


Severity = str  # "low"|"medium"|"high"


@dataclass(frozen=True)
class Finding:
    type: str
    severity: Severity
    description: str
    suggested_action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "suggested_action": self.suggested_action,
        }


def _ensure_tz_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _default_now(session: Session, store_id: str) -> datetime | None:
    max_ts = session.execute(
        select(func.max(Event.timestamp)).where(Event.store_id == store_id, Event.is_staff.is_(False))
    ).scalar_one()
    if max_ts is None:
        return None
    return _ensure_tz_aware(max_ts)


def _queue_depth_snapshot(
    session: Session,
    *,
    store_id: str,
    now: datetime,
    active_since: datetime,
) -> int:
    """Queue depth at `now` defined as visitors whose latest BILLING zone event is `zone_enter`.

    Only counts visitors whose latest billing-zone event happened after `active_since`.
    """

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
            Event.timestamp <= now,
            Event.zone_id == BILLING_ZONE,
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
            Event.zone_id == BILLING_ZONE,
            Event.timestamp >= active_since,
        )
        .subquery()
    )

    return int(session.execute(select(func.count()).select_from(latest_zone_events)).scalar_one())


def _billing_enter_visitors(
    session: Session,
    *,
    store_id: str,
    start: datetime,
    end: datetime,
) -> int:
    return int(
        session.execute(
            select(func.count(func.distinct(Event.visitor_id))).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.timestamp >= start,
                Event.timestamp <= end,
                Event.zone_id == BILLING_ZONE,
                Event.event_type == "zone_enter",
            )
        ).scalar_one()
    )


def _billing_converted_visitors(
    session: Session,
    *,
    store_id: str,
    start: datetime,
    end: datetime,
) -> int:
    billing_visitors_subq = (
        select(Event.visitor_id)
        .where(
            Event.store_id == store_id,
            Event.is_staff.is_(False),
            Event.timestamp >= start,
            Event.timestamp <= end,
            Event.zone_id == BILLING_ZONE,
            Event.event_type == "zone_enter",
        )
        .distinct()
        .subquery()
    )

    return int(
        session.execute(
            select(func.count(func.distinct(Purchase.visitor_id))).where(
                Purchase.visitor_id.in_(select(billing_visitors_subq.c.visitor_id)),
                Purchase.purchase_timestamp >= start,
                Purchase.purchase_timestamp <= end,
            )
        ).scalar_one()
    )


def _zone_visits(
    session: Session,
    *,
    store_id: str,
    zone_id: str,
    start: datetime,
    end: datetime,
) -> int:
    return int(
        session.execute(
            select(func.count()).where(
                Event.store_id == store_id,
                Event.is_staff.is_(False),
                Event.timestamp >= start,
                Event.timestamp <= end,
                Event.zone_id == zone_id,
                Event.event_type.in_(["zone_enter", "zone_dwell"]),
            )
        ).scalar_one()
    )


def detect_store_anomalies(
    session: Session,
    *,
    store_id: str,
    now: datetime | None = None,
    recent_minutes: int = 5,
    baseline_minutes: int = 60,
    dead_zone_minutes: int = 30,
    zones: Sequence[str] = (ENTRY_ZONE, FOH_ZONE, BILLING_ZONE, TOP_BRANDS_ZONE, BOTTOM_BRANDS_ZONE),
) -> list[dict[str, str]]:
    """Detect operational anomalies for a store.

    Detects:
      1) Queue Spike
      2) Conversion Drop
      3) Dead Zone

    Returns list of dicts in the required shape:
      {"type","severity","description","suggested_action"}

    Notes:
      - Staff visitors are excluded.
      - Uses simple recent-vs-baseline comparisons (configurable windows).
    """

    if now is None:
        now = _default_now(session, store_id)
        if now is None:
            return []

    now = _ensure_tz_aware(now)
    recent_start = now - timedelta(minutes=max(1, int(recent_minutes)))
    baseline_end = recent_start
    baseline_start = baseline_end - timedelta(minutes=max(1, int(baseline_minutes)))

    findings: list[Finding] = []

    # 1) Queue Spike
    # Queue depth is a snapshot metric; compare against a baseline snapshot computed
    # using the same "active" window size.
    baseline_active_since = baseline_end - timedelta(minutes=max(1, int(recent_minutes)))
    recent_q = _queue_depth_snapshot(session, store_id=store_id, now=now, active_since=recent_start)
    baseline_q = _queue_depth_snapshot(
        session,
        store_id=store_id,
        now=baseline_end,
        active_since=baseline_active_since,
    )

    ratio = float(recent_q) / float(max(baseline_q, 1))
    if recent_q >= 3 and ratio >= 2.0:
        if recent_q >= 10 and ratio >= 3.0:
            sev: Severity = "high"
        elif recent_q >= 5:
            sev = "medium"
        else:
            sev = "low"
        findings.append(
            Finding(
                type=QUEUE_SPIKE,
                severity=sev,
                description=(
                    f"Queue depth in {BILLING_ZONE} spiked to {recent_q} (baseline {baseline_q})."
                ),
                suggested_action=(
                    "Open an additional checkout lane, reassign staff to billing, "
                    "or investigate POS slowdowns."
                ),
            )
        )

    # 2) Conversion Drop (billing-enter -> purchase)
    recent_billing = _billing_enter_visitors(session, store_id=store_id, start=recent_start, end=now)
    baseline_billing = _billing_enter_visitors(session, store_id=store_id, start=baseline_start, end=baseline_end)

    recent_conv = (
        float(_billing_converted_visitors(session, store_id=store_id, start=recent_start, end=now)) / float(recent_billing)
        if recent_billing
        else 0.0
    )
    baseline_conv = (
        float(_billing_converted_visitors(session, store_id=store_id, start=baseline_start, end=baseline_end))
        / float(baseline_billing)
        if baseline_billing
        else 0.0
    )

    if baseline_billing >= 5 and baseline_conv > 0 and recent_billing >= 3:
        if recent_conv <= baseline_conv * 0.5:
            drop_ratio = 1.0 - (recent_conv / baseline_conv)
            if drop_ratio >= 0.8:
                sev = "high"
            elif drop_ratio >= 0.5:
                sev = "medium"
            else:
                sev = "low"

            findings.append(
                Finding(
                    type=CONVERSION_DROP,
                    severity=sev,
                    description=(
                        f"Conversion rate dropped from {baseline_conv:.2f} to {recent_conv:.2f} "
                        f"(billing visitors recent={recent_billing}, baseline={baseline_billing})."
                    ),
                    suggested_action=(
                        "Check checkout throughput, pricing/promotions, and staff availability; "
                        "verify POS is recording transactions correctly."
                    ),
                )
            )

    # 3) Dead Zone
    dead_start = now - timedelta(minutes=max(1, int(dead_zone_minutes)))
    history_start = now - timedelta(hours=24)

    for zid in zones:
        if zid == BILLING_ZONE:
            # Billing being empty can be normal; we don't treat it as dead zone here.
            continue

        recent_visits = _zone_visits(session, store_id=store_id, zone_id=zid, start=dead_start, end=now)
        if recent_visits > 0:
            continue

        history_visits = _zone_visits(session, store_id=store_id, zone_id=zid, start=history_start, end=dead_start)
        if history_visits >= 5:
            findings.append(
                Finding(
                    type=DEAD_ZONE,
                    severity="medium",
                    description=(
                        f"Zone {zid} has had no visits in the last {dead_zone_minutes} minutes "
                        f"(historical visits in prior 24h: {history_visits})."
                    ),
                    suggested_action=(
                        "Check camera coverage and zone polygons, look for obstructions, "
                        "and verify traffic flow (signage/layout)."
                    ),
                )
            )

    return [f.to_dict() for f in findings]
