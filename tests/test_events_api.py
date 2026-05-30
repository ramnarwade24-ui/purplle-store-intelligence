from __future__ import annotations

from datetime import datetime, timezone


def test_ingest_and_metrics(client):
    now = datetime.now(timezone.utc).isoformat()
    payload = [
        {"timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "enter"},
        {
            "timestamp": now,
            "store_id": "store-01",
            "camera_id": "cam-1",
            "visitor_id": "1",
            "event_type": "position",
            "payload": {"cx": 10, "cy": 20},
        },
        {"timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "1", "event_type": "exit"},
        {"timestamp": now, "store_id": "store-01", "camera_id": "cam-1", "visitor_id": "2", "event_type": "enter"},
    ]
    r = client.post("/v1/events", json=payload)
    assert r.status_code == 200
    assert r.json()["inserted"] == len(payload)

    m = client.get("/v1/metrics/visitors", params={"camera_id": "cam-1"})
    assert m.status_code == 200
    data = m.json()
    assert data["unique_visitors"] == 2
    assert data["enters"] == 2
    assert data["exits"] == 1

    f = client.get("/v1/funnel", params={"camera_id": "cam-1", "steps": ["enter", "exit"]})
    assert f.status_code == 200
    funnel = f.json()
    assert len(funnel) == 2

