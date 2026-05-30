from __future__ import annotations

from collections.abc import Iterable

import cv2

from storeintel.core.settings import Settings
from storeintel.video.detector_yolov8 import YoloV8Detector
from storeintel.video.events import EventGenerator
from storeintel.video.tracker_bytetrack import ByteTrackTracker


class VideoPipeline:
    def __init__(
        self,
        *,
        detector: YoloV8Detector,
        tracker: ByteTrackTracker,
        event_generator: EventGenerator,
        frame_stride: int = 3,
    ):
        self._detector = detector
        self._tracker = tracker
        self._events = event_generator
        self._stride = max(1, frame_stride)

    @classmethod
    def from_settings(cls, settings: Settings) -> "VideoPipeline":
        detector = YoloV8Detector(settings.yolo_model, conf=settings.yolo_conf)
        tracker = ByteTrackTracker(track_buffer=settings.processor_track_buffer_frames)
        generator = EventGenerator(
            position_event_every_n_frames=settings.processor_position_event_every_n_frames,
            track_buffer_frames=settings.processor_track_buffer_frames,
        )
        return cls(detector=detector, tracker=tracker, event_generator=generator, frame_stride=settings.processor_frame_stride)

    def process_video(self, video_path: str, *, camera_id: str) -> Iterable[dict]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_index % self._stride != 0:
                frame_index += 1
                continue

            detections = self._detector.detect_people(frame)
            tracks = self._tracker.update(frame, detections)
            for ev in self._events.step(frame_index=frame_index, camera_id=camera_id, tracks=tracks):
                yield ev

            frame_index += 1

        cap.release()
