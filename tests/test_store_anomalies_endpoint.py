from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from storeintel.db.database import get_sessionmaker
from storeintel.db.models import Purchase
from storeintel.video.zone_manager import BILLING_ZONE, FOH_ZONE


def test_get_store_anomalies_returns_active_supported_anomalies(client):
    store_id = "store-1"
    camera_id = "cam-1"
    now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)

    recent_start = now - timedelta(minutes=5)
    baseline_end = recent_start
    baseline_start = baseline_end - timedelta(minutes=60)
    dead_start = now - timedelta(minutes=30)

    events: list[dict] = []

    # Baseline queue snapshot: 1 visitor in billing close to baseline_end
    events.append(
        {
            "store_id": store_id,
            "camera_id": camera_id,
            "visitor_id": "b0",
            "event_type": "zone_enter",
            "timestamp": (baseline_end - timedelta(minutes=2)).isoformat(),
            "zone_id": BILLING_ZONE,
            "metadata": {},
        }
    )

    # Recent queue: 5 visitors enter billing and don't exit
    for i in range(5):
        events.append(
            {
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": f"q{i}",
                "event_type": "zone_enter",
                "timestamp": (recent_start + timedelta(seconds=30 + i)).isoformat(),
                "zone_id": BILLING_ZONE,
                "metadata": {},
            }
        )

    # Conversion baseline: 10 billing visitors
    for i in range(10):
        events.append(
            {
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": f"cb{i}",
                "event_type": "zone_enter",
                "timestamp": (baseline_start + timedelta(minutes=20, seconds=i)).isoformat(),
                "zone_id": BILLING_ZONE,
                "metadata": {},
            }
        )

    # Conversion recent: 10 billing visitors
    for i in range(10):
        events.append(
            {
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": f"cr{i}",
                "event_type": "zone_enter",
                "timestamp": (recent_start + timedelta(seconds=90 + i)).isoformat(),
                "zone_id": BILLING_ZONE,
                "metadata": {},
            }
        )

    # Dead zone: FOH had traffic earlier, none in last 30 minutes
    for i in range(6):
        events.append(
            {
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": f"foh{i}",
                "event_type": "zone_enter",
                "timestamp": (dead_start - timedelta(minutes=10, seconds=i)).isoformat(),
                "zone_id": FOH_ZONE,
                "metadata": {},
            }
        )

    ing = client.post("/events/ingest", json=events)
    assert ing.status_code == 200

    # Purchases: baseline 5 conversions, recent 0 conversions
    db_path = os.environ["SQLITE_PATH"]
    SessionLocal = get_sessionmaker(db_path)
    with SessionLocal() as session:
        for i in range(5):
            session.add(
                Purchase(
                    visitor_id=f"cb{i}",
                    transaction_id=f"txb-{i}",
                    purchase_amount=10.0,
                    purchase_timestamp=baseline_start + timedelta(minutes=22, seconds=i),
                )
            )
        session.commit()

    r = client.get(f"/stores/{store_id}/anomalies")
    assert r.status_code == 200

    body = r.json()
    assert isinstance(body, list)
    assert body, "expected at least one anomaly"

    for item in body:
        assert set(item.keys()) == {"type", "severity", "description", "suggested_action"}
        assert item["type"] in {"QUEUE_SPIKE", "CONVERSION_DROP", "DEAD_ZONE"}
        assert item["severity"] in {"WARN", "CRIT"}
        assert isinstance(item["description"], str)
        assert isinstance(item["suggested_action"], str)

    types = {a["type"] for a in body}
    assert "QUEUE_SPIKE" in types
    assert "CONVERSION_DROP" in types
    assert "DEAD_ZONE" in types
