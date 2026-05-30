from __future__ import annotations

from datetime import datetime, timedelta, timezone

from storeintel.analytics.anomaly_engine import (
    CONVERSION_DROP,
    DEAD_ZONE,
    QUEUE_SPIKE,
    detect_store_anomalies,
)
from storeintel.db.database import get_sessionmaker, init_db
from storeintel.db.models import Event, Purchase, Store
from storeintel.video.zone_manager import BILLING_ZONE, FOH_ZONE


def test_anomaly_engine_detects_queue_spike_conversion_drop_and_dead_zone(tmp_path):
    db_path = tmp_path / "anomaly.db"
    init_db(str(db_path))
    SessionLocal = get_sessionmaker(str(db_path))

    store_id = "store-1"
    camera_id = "cam-1"
    now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)

    with SessionLocal() as session:
        session.add(Store(store_id=store_id, name="Test Store"))

        # Windows: baseline 60m ending 5m ago; recent last 5m.
        recent_start = now - timedelta(minutes=5)
        baseline_end = recent_start
        baseline_start = baseline_end - timedelta(minutes=60)
        dead_start = now - timedelta(minutes=30)

        # Baseline: small queue (1 visitor still in billing) within the snapshot window
        session.add(
            Event(
                store_id=store_id,
                camera_id=camera_id,
                visitor_id="b0",
                event_type="zone_enter",
            timestamp=baseline_end - timedelta(minutes=2),
                zone_id=BILLING_ZONE,
                dwell_ms=None,
                is_staff=False,
                confidence=0.9,
                payload={},
            )
        )

        # Recent: bigger queue (5 visitors enter billing and do not exit)
        for i in range(5):
            session.add(
                Event(
                    store_id=store_id,
                    camera_id=camera_id,
                    visitor_id=f"q{i}",
                    event_type="zone_enter",
                    timestamp=recent_start + timedelta(seconds=30 + i),
                    zone_id=BILLING_ZONE,
                    dwell_ms=None,
                    is_staff=False,
                    confidence=0.9,
                    payload={},
                )
            )

        # Conversion baseline: 10 billing visitors, 5 purchases
        for i in range(10):
            vid = f"cb{i}"
            session.add(
                Event(
                    store_id=store_id,
                    camera_id=camera_id,
                    visitor_id=vid,
                    event_type="zone_enter",
                    timestamp=baseline_start + timedelta(minutes=20, seconds=i),
                    zone_id=BILLING_ZONE,
                    dwell_ms=None,
                    is_staff=False,
                    confidence=0.9,
                    payload={},
                )
            )

        for i in range(5):
            session.add(
                Purchase(
                    visitor_id=f"cb{i}",
                    transaction_id=f"txb-{i}",
                    purchase_amount=10.0,
                    purchase_timestamp=baseline_start + timedelta(minutes=22, seconds=i),
                )
            )

        # Conversion recent: 10 billing visitors, 0 purchases
        for i in range(10):
            session.add(
                Event(
                    store_id=store_id,
                    camera_id=camera_id,
                    visitor_id=f"cr{i}",
                    event_type="zone_enter",
                    timestamp=recent_start + timedelta(seconds=90 + i),
                    zone_id=BILLING_ZONE,
                    dwell_ms=None,
                    is_staff=False,
                    confidence=0.9,
                    payload={},
                )
            )

        # Dead zone: FOH had traffic in last 24h before dead window, none in last 30m
        for i in range(6):
            session.add(
                Event(
                    store_id=store_id,
                    camera_id=camera_id,
                    visitor_id=f"foh{i}",
                    event_type="zone_enter",
                    timestamp=dead_start - timedelta(minutes=10, seconds=i),
                    zone_id=FOH_ZONE,
                    dwell_ms=None,
                    is_staff=False,
                    confidence=0.9,
                    payload={},
                )
            )

        session.commit()

        findings = detect_store_anomalies(
            session,
            store_id=store_id,
            now=now,
            recent_minutes=5,
            baseline_minutes=60,
            dead_zone_minutes=30,
            zones=(FOH_ZONE,),
        )

    # Validate shape
    assert all(set(f.keys()) == {"type", "severity", "description", "suggested_action"} for f in findings)

    types = {f["type"] for f in findings}
    assert QUEUE_SPIKE in types
    assert CONVERSION_DROP in types
    assert DEAD_ZONE in types
