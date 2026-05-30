from __future__ import annotations

from typing import Any

import numpy as np

from storeintel.video.types import Detection, Track


class ByteTrackTracker:
    def __init__(self, *, track_buffer: int = 30):
        # Use supervision's ByteTrack implementation.
        import supervision as sv  # type: ignore

        self._sv = sv
        self._tracker = sv.ByteTrack(track_buffer=track_buffer)

    def update(self, frame_bgr: np.ndarray, detections: list[Detection]) -> list[Track]:
        if not detections:
            # Still advance tracker with empty detections
            tracked = self._tracker.update_with_detections(self._sv.Detections.empty())
            return [] if tracked is None else []

        xyxy = np.array([[d.x1, d.y1, d.x2, d.y2] for d in detections], dtype=np.float32)
        conf = np.array([d.confidence for d in detections], dtype=np.float32)
        class_id = np.array([d.class_id for d in detections], dtype=np.int32)

        det = self._sv.Detections(xyxy=xyxy, confidence=conf, class_id=class_id)
        tracked: Any = self._tracker.update_with_detections(det)
        out: list[Track] = []
        if tracked is None or tracked.tracker_id is None:
            return out

        for i in range(len(tracked)):
            tid = int(tracked.tracker_id[i])
            x1, y1, x2, y2 = [float(v) for v in tracked.xyxy[i].tolist()]
            c = float(tracked.confidence[i]) if tracked.confidence is not None else 1.0
            out.append(Track(track_id=tid, x1=x1, y1=y1, x2=x2, y2=y2, confidence=c))
        return out
