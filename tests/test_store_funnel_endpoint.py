from __future__ import annotations

from datetime import datetime, timedelta, timezone

from storeintel.core.settings import get_settings
from storeintel.db.database import get_sessionmaker
from storeintel.db.models import Purchase


def _stage(data, name: str):
    return next(s for s in data["stages"] if s["stage"] == name)


def test_store_funnel_session_based_reentry_and_dropoffs(client):
    t0 = datetime(2026, 5, 30, 10, 0, 0, tzinfo=timezone.utc)

    # Sessions:
    # v1: session1 enters -> zone visit -> billing -> purchase -> exits
    # v1: session2 re-enters later -> zone visit only -> exits
    # v2: enters -> zone visit -> billing -> exits (no purchase)
    events = [
        # v1 session 1
        {"timestamp": (t0 + timedelta(seconds=0)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "enter"},
        {"timestamp": (t0 + timedelta(seconds=5)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "zone_enter", "zone_id": "FOH_ZONE"},
        {"timestamp": (t0 + timedelta(seconds=10)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "zone_enter", "zone_id": "BILLING_ZONE"},
        {"timestamp": (t0 + timedelta(seconds=20)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "exit"},
        # v1 session 2 (re-entry)
        {"timestamp": (t0 + timedelta(minutes=10)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "enter"},
        {"timestamp": (t0 + timedelta(minutes=10, seconds=5)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "zone_enter", "zone_id": "FOH_ZONE"},
        {"timestamp": (t0 + timedelta(minutes=10, seconds=20)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "exit"},
        # v2 session
        {"timestamp": (t0 + timedelta(seconds=1)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "2", "event_type": "enter"},
        {"timestamp": (t0 + timedelta(seconds=6)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "2", "event_type": "zone_enter", "zone_id": "FOH_ZONE"},
        {"timestamp": (t0 + timedelta(seconds=12)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "2", "event_type": "zone_enter", "zone_id": "BILLING_ZONE"},
        {"timestamp": (t0 + timedelta(seconds=25)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "2", "event_type": "exit"},
        # staff should be excluded
        {"timestamp": (t0 + timedelta(seconds=2)).isoformat(), "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "staff-1", "event_type": "enter", "is_staff": True},
    ]

    r = client.post("/v1/events", json=events)
    assert r.status_code == 200

    # Purchase for v1 session1 within its window
    settings = get_settings()
    SessionLocal = get_sessionmaker(settings.sqlite_path)
    with SessionLocal() as s:
        s.add(
            Purchase(
                visitor_id="1",
                transaction_id="tx-100",
                purchase_amount=10.0,
                purchase_timestamp=t0 + timedelta(seconds=15),
            )
        )
        s.commit()

    f = client.get("/stores/store-01/funnel")
    assert f.status_code == 200
    data = f.json()

    assert data["sessions"] == 3

    assert _stage(data, "ENTRY")["count"] == 3
    assert _stage(data, "ZONE_VISIT")["count"] == 3
    assert _stage(data, "BILLING")["count"] == 2
    assert _stage(data, "PURCHASE")["count"] == 1

    assert _stage(data, "ZONE_VISIT")["dropoff_pct"] == 0.0

    billing_drop = _stage(data, "BILLING")["dropoff_pct"]
    assert abs(billing_drop - (1 / 3) * 100.0) < 1e-6

    purchase_drop = _stage(data, "PURCHASE")["dropoff_pct"]
    assert abs(purchase_drop - 50.0) < 1e-6
