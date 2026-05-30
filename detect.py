from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2


def _iter_person_detections_ultralytics(result) -> list[dict[str, Any]]:
    """Convert an Ultralytics `Results` into JSON-serializable dicts.

    Assumes the model call was already filtered to person class.
    Output fields:
      - bbox: [x1, y1, x2, y2]
      - confidence: float
    """

    if result is None or result.boxes is None:
        return []

    boxes_xyxy = result.boxes.xyxy
    confs = result.boxes.conf

    xyxy_list = boxes_xyxy.tolist() if hasattr(boxes_xyxy, "tolist") else list(boxes_xyxy)
    conf_list = confs.tolist() if hasattr(confs, "tolist") else list(confs)

    out: list[dict[str, Any]] = []
    for xyxy, conf in zip(xyxy_list, conf_list, strict=False):
        x1, y1, x2, y2 = (int(round(v)) for v in xyxy)
        out.append({"bbox": [x1, y1, x2, y2], "confidence": float(conf)})
    return out


def detect_videos_to_json(
    *,
    input_paths: list[str | Path],
    output_json_path: str | Path,
    model_path: str = "yolov8n.pt",
    conf: float = 0.25,
) -> dict[str, list[dict[str, Any]]]:
    """Run person-only detection on multiple videos and write detections.json.

    Output JSON structure:
      {
        "videos": {
          "videos/CAM1.mp4": [
            {"frame_number": 0, "bbox": [x1,y1,x2,y2], "confidence": 0.9, "timestamp": 0.0},
            ...
          ],
          ...
        }
      }
    """

    # Lazy import so `python -m py_compile detect.py` works without ultralytics installed.
    from ultralytics import YOLO  # type: ignore

    output_json_path = Path(output_json_path)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)

    model = YOLO(model_path)

    per_video: dict[str, list[dict[str, Any]]] = {}

    for input_path in input_paths:
        input_path = Path(input_path)
        key = input_path.as_posix()

        cap = cv2.VideoCapture(str(input_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open input video: {input_path}")

        detections: list[dict[str, Any]] = []
        frame_number = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                # Timestamp in seconds from start of the video.
                timestamp_s = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0

                results = model.predict(
                    source=frame,
                    conf=conf,
                    classes=[0],  # COCO person
                    verbose=False,
                )
                result = results[0] if results else None

                for det in _iter_person_detections_ultralytics(result):
                    detections.append(
                        {
                            "frame_number": frame_number,
                            "bbox": det["bbox"],
                            "confidence": det["confidence"],
                            "timestamp": timestamp_s,
                        }
                    )

                frame_number += 1
        finally:
            cap.release()

        per_video[key] = detections

    payload = {"videos": per_video}
    output_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return per_video


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLOv8 person-only detector -> detections.json (OpenCV + Ultralytics)")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=["videos/CAM1.mp4", "videos/CAM2.mp4", "videos/CAM3.mp4"],
        help="Input video paths (default: videos/CAM1.mp4 videos/CAM2.mp4 videos/CAM3.mp4)",
    )
    parser.add_argument(
        "--output",
        default="detections.json",
        help="Output JSON path (default: detections.json)",
    )
    parser.add_argument(
        "--model",
        default="yolov8n.pt",
        help="Ultralytics model path/name (default: yolov8n.pt)",
    )
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    args = parser.parse_args()

    _ = detect_videos_to_json(input_paths=args.inputs, output_json_path=args.output, model_path=args.model, conf=args.conf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
