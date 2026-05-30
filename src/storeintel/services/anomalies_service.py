from __future__ import annotations

from sqlalchemy.orm import Session

from storeintel.analytics.anomaly_engine import (
    CONVERSION_DROP,
    DEAD_ZONE,
    QUEUE_SPIKE,
    detect_store_anomalies,
)


SUPPORTED_TYPES = {QUEUE_SPIKE, CONVERSION_DROP, DEAD_ZONE}


def _map_severity(engine_severity: str) -> str:
    # API uses a small set of severities.
    # Map the engine's low/medium/high into WARN/CRIT.
    if engine_severity.lower() == "high":
        return "CRIT"
    return "WARN"


def get_active_anomalies(session: Session, *, store_id: str) -> list[dict[str, str]]:
    findings = detect_store_anomalies(session, store_id=store_id)

    out: list[dict[str, str]] = []
    for f in findings:
        anomaly_type = str(f.get("type") or "")
        if anomaly_type not in SUPPORTED_TYPES:
            continue

        out.append(
            {
                "type": anomaly_type,
                "severity": _map_severity(str(f.get("severity") or "")),
                "description": str(f.get("description") or ""),
                "suggested_action": str(f.get("suggested_action") or ""),
            }
        )

    return out
