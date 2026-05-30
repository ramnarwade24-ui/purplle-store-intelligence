from __future__ import annotations

from typing import Any

import numpy as np

from storeintel.video.types import Detection


class YoloV8Detector:
    def __init__(self, model_path: str, conf: float = 0.25):
        # Import lazily so unit tests (and minimal installs) can still run.
        from ultralytics import YOLO  # type: ignore

        self._model = YOLO(model_path)
        self._conf = conf

    def detect_people(self, frame_bgr: np.ndarray) -> list[Detection]:
        # Ultralytics returns boxes in xyxy
        results = self._model.predict(frame_bgr, conf=self._conf, verbose=False)
        dets: list[Detection] = []
        if not results:
            return dets
        r0: Any = results[0]
        if r0.boxes is None:
            return dets
        for box in r0.boxes:
            cls = int(box.cls.item())
            # COCO person class == 0
            if cls != 0:
                continue
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            conf = float(box.conf.item())
            dets.append(Detection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf, class_id=cls))
        return dets
