from __future__ import annotations

from datetime import datetime, timedelta, timezone

from storeintel.core.settings import get_settings
from storeintel.db.database import get_sessionmaker
from storeintel.db.models import Purchase


def test_store_metrics_excludes_staff_and_computes_rates(client):
    now = datetime(2026, 5, 30, 0, 0, 0, tzinfo=timezone.utc)

    # Seed events for store-01
    events = [
        # visitor 1 enters billing, then exits
        {
            "timestamp": (now + timedelta(seconds=0)).isoformat(),
            "store_id": "store-01",
            "camera_id": "cam-1",
            "visitor_id": "1",
            "event_type": "zone_enter",
            "zone_id": "BILLING_ZONE",
        },
        {
            "timestamp": (now + timedelta(seconds=10)).isoformat(),
            "store_id": "store-01",
            "camera_id": "cam-1",
            "visitor_id": "1",
            "event_type": "zone_dwell",
            "zone_id": "BILLING_ZONE",
            "dwell_ms": 30000,
        },
        {
            "timestamp": (now + timedelta(seconds=20)).isoformat(),
            "store_id": "store-01",
            "camera_id": "cam-1",
            "visitor_id": "1",
            "event_type": "zone_exit",
            "zone_id": "BILLING_ZONE",
        },
        # visitor 2 enters billing and stays (queue)
        {
            "timestamp": (now + timedelta(seconds=5)).isoformat(),
            "store_id": "store-01",
            "camera_id": "cam-1",
            "visitor_id": "2",
            "event_type": "zone_enter",
            "zone_id": "BILLING_ZONE",
        },
        {
            "timestamp": (now + timedelta(seconds=12)).isoformat(),
            "store_id": "store-01",
            "camera_id": "cam-1",
            "visitor_id": "2",
            "event_type": "zone_dwell",
            "zone_id": "BILLING_ZONE",
            "dwell_ms": 10000,
        },
        # staff visitor should be excluded
        {
            "timestamp": (now + timedelta(seconds=1)).isoformat(),
            "store_id": "store-01",
            "camera_id": "cam-1",
            "visitor_id": "staff-1",
            "event_type": "zone_enter",
            "zone_id": "BILLING_ZONE",
            "is_staff": True,
        },
    ]

    r = client.post("/v1/events", json=events)
    assert r.status_code == 200

    # Insert a purchase for visitor 1
    settings = get_settings()
    SessionLocal = get_sessionmaker(settings.sqlite_path)
    with SessionLocal() as session:
        session.add(
            Purchase(
                visitor_id="1",
                transaction_id="tx-1",
                purchase_amount=25.0,
                purchase_timestamp=now + timedelta(minutes=1),
            )
        )
        session.commit()

    m = client.get("/stores/store-01/metrics")
    assert m.status_code == 200
    data = m.json()

    assert data["unique_visitors"] == 2  # staff excluded
    assert data["conversion_rate"] == 0.5
    assert data["avg_dwell_time"] == 20000.0  # avg of 30000 and 10000
    assert data["queue_depth"] == 1  # visitor 2 still in billing
    assert data["abandonment_rate"] == 0.5  # 1 of 2 billing visitors did not purchase
