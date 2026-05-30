from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Anomaly:
    bucket_start: datetime
    count: int
    zscore: float


def detect_count_anomalies(
    timestamps: list[datetime],
    *,
    bucket_seconds: int = 3600,
    z_threshold: float = 3.0,
) -> list[Anomaly]:
    if not timestamps:
        return []

    out_tz = timestamps[0].tzinfo

    # Bucket by epoch
    def bucket(ts: datetime) -> int:
        return int(ts.timestamp()) // bucket_seconds

    counts = Counter(bucket(ts) for ts in timestamps)
    keys = sorted(counts)
    series = [counts[k] for k in keys]
    mean = sum(series) / len(series)
    var = sum((x - mean) ** 2 for x in series) / max(len(series), 1)
    std = var ** 0.5
    if std == 0:
        return []

    anomalies: list[Anomaly] = []
    for k in keys:
        c = counts[k]
        z = (c - mean) / std
        if abs(z) >= z_threshold:
            bucket_epoch = k * bucket_seconds
            anomalies.append(
                Anomaly(
                    bucket_start=(
                        datetime.fromtimestamp(bucket_epoch, tz=out_tz)
                        if out_tz is not None
                        else datetime.fromtimestamp(bucket_epoch)
                    ),
                    count=c,
                    zscore=z,
                )
            )
    return anomalies
