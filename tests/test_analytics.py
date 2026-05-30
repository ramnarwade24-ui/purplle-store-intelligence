from __future__ import annotations

from datetime import datetime, timedelta, timezone

from storeintel.analytics.anomaly import detect_count_anomalies


def test_detect_count_anomalies_smoke():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = []
    # mostly 10 per hour
    for h in range(24):
        for _ in range(10):
            ts.append(start + timedelta(hours=h, minutes=_))
    # add a spike
    for _ in range(60):
        ts.append(start + timedelta(hours=12, minutes=30, seconds=_))

    anomalies = detect_count_anomalies(ts, bucket_seconds=3600, z_threshold=2.5)
    assert any(a.bucket_start.hour == 12 for a in anomalies)
