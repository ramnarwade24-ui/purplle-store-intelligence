from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


@dataclass(frozen=True)
class YoloDetection:
    frame_number: int
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    confidence: float
    timestamp: float


def _parse_detection(obj: dict[str, Any]) -> YoloDetection:
    try:
        frame_number = int(obj["frame_number"])
        bbox_raw = obj["bbox"]
        confidence = float(obj["confidence"])
        timestamp = float(obj["timestamp"])
    except KeyError as e:
        raise ValueError(f"Missing required key: {e.args[0]}") from e
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid detection fields: {e}") from e

    if not isinstance(bbox_raw, (list, tuple)) or len(bbox_raw) != 4:
        raise ValueError("bbox must be a 4-element list/tuple [x1,y1,x2,y2]")

    x1, y1, x2, y2 = (float(v) for v in bbox_raw)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox must have x2 > x1 and y2 > y1")

    # YOLO/Ultralytics confidence is typically 0..1, but don't hard fail if slightly outside.
    if not np.isfinite(confidence) or confidence < 0.0:
        raise ValueError("confidence must be a finite non-negative number")

    if frame_number < 0:
        raise ValueError("frame_number must be >= 0")
    if not np.isfinite(timestamp) or timestamp < 0.0:
        raise ValueError("timestamp must be a finite number in seconds >= 0")

    return YoloDetection(
        frame_number=frame_number,
        bbox=(x1, y1, x2, y2),
        confidence=confidence,
        timestamp=timestamp,
    )


def _group_by_frame(detections: Iterable[YoloDetection]) -> list[tuple[int, float, list[YoloDetection]]]:
    by_frame: dict[int, list[YoloDetection]] = {}
    for d in detections:
        by_frame.setdefault(d.frame_number, []).append(d)

    frames: list[tuple[int, float, list[YoloDetection]]] = []
    for frame_number in sorted(by_frame.keys()):
        ds = by_frame[frame_number]
        # Detections.json provides timestamp per detection; use the max for stability.
        ts = max(d.timestamp for d in ds)
        frames.append((frame_number, ts, ds))
    return frames


def track_people_bytetrack(
    *,
    detections: Iterable[dict[str, Any]] | Iterable[YoloDetection],
    track_buffer: int = 30,
) -> list[dict[str, Any]]:
    """Track people across frames using ByteTrack.

    Input detections are expected to be person-only YOLO detections with fields:
      - frame_number: int
      - bbox: [x1,y1,x2,y2]
      - confidence: float
      - timestamp: float (seconds from video start)

    Output records contain ONLY:
      - track_id: int
      - bbox: [x1,y1,x2,y2]
      - timestamp: float

    The output contains one record per tracked box per frame.
    """

    # Supervision's ByteTrack implementation.
    import supervision as sv  # type: ignore
    import inspect

    parsed: list[YoloDetection] = []
    for item in detections:
        if isinstance(item, YoloDetection):
            parsed.append(item)
        else:
            if not isinstance(item, dict):
                raise ValueError("detections must be dicts or YoloDetection objects")
            parsed.append(_parse_detection(item))

    # Supervision deprecated `track_buffer` in favor of `lost_track_buffer`.
    sig = inspect.signature(sv.ByteTrack)
    if "lost_track_buffer" in sig.parameters:
        tracker = sv.ByteTrack(lost_track_buffer=track_buffer)
    else:
        tracker = sv.ByteTrack(track_buffer=track_buffer)

    out: list[dict[str, Any]] = []

    for _frame_number, ts, frame_dets in _group_by_frame(parsed):
        if not frame_dets:
            _ = tracker.update_with_detections(sv.Detections.empty())
            continue

        xyxy = np.array([d.bbox for d in frame_dets], dtype=np.float32)
        conf = np.array([d.confidence for d in frame_dets], dtype=np.float32)
        class_id = np.zeros((len(frame_dets),), dtype=np.int32)  # person-only

        det = sv.Detections(xyxy=xyxy, confidence=conf, class_id=class_id)
        tracked = tracker.update_with_detections(det)
        if tracked is None or tracked.tracker_id is None:
            continue

        # tracked.xyxy is float; emit ints for bbox for consistency with detector output.
        for i in range(len(tracked)):
            tid = int(tracked.tracker_id[i])
            x1, y1, x2, y2 = tracked.xyxy[i].tolist()
            out.append(
                {
                    "track_id": tid,
                    "bbox": [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))],
                    "timestamp": float(ts),
                }
            )

    return out


def track_detections_json(
    *,
    input_json_path: str | Path = "detections.json",
    output_json_path: str | Path = "tracks.json",
    track_buffer: int = 30,
) -> dict[str, list[dict[str, Any]]]:
    """Read detections.json (from detect.py) and write tracks.json.

    Input format:
      {"videos": {"videos/CAM1.mp4": [ {frame_number,bbox,confidence,timestamp}, ... ], ... }}

    Output format:
      {"videos": {"videos/CAM1.mp4": [ {track_id,bbox,timestamp}, ... ], ... }}
    """

    input_json_path = Path(input_json_path)
    output_json_path = Path(output_json_path)

    raw = json.loads(input_json_path.read_text(encoding="utf-8"))
    videos = raw.get("videos")
    if not isinstance(videos, dict):
        raise ValueError("Expected JSON object with top-level key 'videos'")

    out: dict[str, list[dict[str, Any]]] = {}
    for video_key, det_list in videos.items():
        if not isinstance(video_key, str):
            raise ValueError("Video keys must be strings")
        if not isinstance(det_list, list):
            raise ValueError(f"Expected list of detections for video '{video_key}'")

        out[video_key] = track_people_bytetrack(detections=det_list, track_buffer=track_buffer)

    output_json_path.write_text(json.dumps({"videos": out}, indent=2), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="ByteTrack people tracker for YOLO detections.json")
    parser.add_argument("--input", default="detections.json", help="Input detections JSON (default: detections.json)")
    parser.add_argument("--output", default="tracks.json", help="Output tracks JSON (default: tracks.json)")
    parser.add_argument("--track-buffer", type=int, default=30, help="ByteTrack track_buffer (default: 30)")
    args = parser.parse_args()

    track_detections_json(
        input_json_path=args.input,
        output_json_path=args.output,
        track_buffer=args.track_buffer,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
