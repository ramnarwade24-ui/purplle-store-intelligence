from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_health_no_events_is_stale(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service_status"] in {"ok", "degraded"}
    assert body["database_status"] in {"ok", "error"}
    assert body["last_event_timestamp"] is None
    assert body["stale_feed_warning"] is True


def test_health_recent_event_not_stale(client):
    now = datetime.now(timezone.utc)
    payload = [
        {
            "store_id": "store-1",
            "camera_id": "cam-1",
            "visitor_id": "v1",
            "event_type": "enter",
            "timestamp": now.isoformat(),
            "metadata": {},
        }
    ]
    ing = client.post("/events/ingest", json=payload)
    assert ing.status_code == 200

    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database_status"] == "ok"
    assert body["last_event_timestamp"] is not None
    assert body["stale_feed_warning"] is False


def test_health_old_event_is_stale(client):
    old = datetime.now(timezone.utc) - timedelta(minutes=11)
    payload = [
        {
            "store_id": "store-1",
            "camera_id": "cam-1",
            "visitor_id": "v1",
            "event_type": "enter",
            "timestamp": old.isoformat(),
            "metadata": {},
        }
    ]
    ing = client.post("/events/ingest", json=payload)
    assert ing.status_code == 200

    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database_status"] == "ok"
    assert body["last_event_timestamp"] is not None
    assert body["stale_feed_warning"] is True
