from __future__ import annotations

from datetime import datetime, timezone


def test_events_ingest_partial_success_and_dedup(client):
    now = datetime.now(timezone.utc).isoformat()

    eid = "11111111-1111-1111-1111-111111111111"

    payload = [
        # valid
        {"event_id": eid, "timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "enter"},
        # duplicate within batch
        {"event_id": eid, "timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "enter"},
        # invalid (missing store_id)
        {"timestamp": now, "camera_id": "cam-1", "visitor_id": "1", "event_type": "enter"},
        # valid without event_id
        {"timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "2", "event_type": "enter"},
    ]

    r = client.post("/events/ingest", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["accepted"] == 2
    assert data["duplicates"] == 1
    assert data["failed"] == 1

    # Re-ingest the same event_id should be counted as duplicate (DB dedup)
    r2 = client.post(
        "/events/ingest",
        json=[
            {"event_id": eid, "timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "enter"}
        ],
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["accepted"] == 0
    assert data2["duplicates"] == 1
    assert data2["failed"] == 0


def test_events_ingest_max_batch_size(client):
    now = datetime.now(timezone.utc).isoformat()
    payload = [
        {"timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": str(i), "event_type": "enter"}
        for i in range(501)
    ]
    r = client.post("/events/ingest", json=payload)
    assert r.status_code == 413
