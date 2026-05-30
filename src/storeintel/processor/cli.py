from __future__ import annotations

import argparse
from datetime import datetime, timezone

import httpx

from storeintel.core.logging import configure_logging, get_logger
from storeintel.core.settings import get_settings
from storeintel.video.pipeline import VideoPipeline


def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    log = get_logger(__name__)

    parser = argparse.ArgumentParser(description="CCTV processor -> visitor events")
    parser.add_argument("--video", required=True, help="Path to CCTV footage")
    parser.add_argument("--store-id", default="store-01")
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--api-url", default=settings.api_base_url)
    args = parser.parse_args()

    pipeline = VideoPipeline.from_settings(settings)
    events_batch: list[dict] = []

    with httpx.Client(timeout=30.0) as client:
        for event in pipeline.process_video(args.video, camera_id=args.camera_id):
            events_batch.append(
                {
                    "store_id": args.store_id,
                    "camera_id": event["camera_id"],
                    "visitor_id": str(event.get("track_id") or "unknown"),
                    "event_type": event["event_name"],
                    "timestamp": event["timestamp"],
                    "zone_id": event.get("zone_id"),
                    "dwell_ms": event.get("dwell_ms"),
                    "is_staff": bool(event.get("is_staff", False)),
                    "confidence": event.get("confidence"),
                    "payload": {
                        **(event.get("payload") or {}),
                        "x1": event.get("x1"),
                        "y1": event.get("y1"),
                        "x2": event.get("x2"),
                        "y2": event.get("y2"),
                        "cx": event.get("cx"),
                        "cy": event.get("cy"),
                        "track_id": event.get("track_id"),
                    },
                }
            )
            if len(events_batch) >= settings.processor_batch_size:
                _flush(client, args.api_url, events_batch)
                events_batch = []
        if events_batch:
            _flush(client, args.api_url, events_batch)

    log.info("processor_complete", video=args.video, at=datetime.now(timezone.utc).isoformat())


def _flush(client: httpx.Client, api_url: str, events: list[dict]) -> None:
    log = get_logger(__name__)
    url = api_url.rstrip("/") + "/v1/events"
    r = client.post(url, json=events)
    r.raise_for_status()
    log.info("events_sent", url=url, inserted=r.json().get("inserted"), batch=len(events))

