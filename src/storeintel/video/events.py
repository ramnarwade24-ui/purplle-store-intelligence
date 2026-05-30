from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from storeintel.video.types import Track


@dataclass
class TrackState:
    last_seen_frame: int
    active: bool = True


class EventGenerator:
    def __init__(
        self,
        *,
        position_event_every_n_frames: int = 5,
        track_buffer_frames: int = 30,
    ):
        self._pos_every = max(1, position_event_every_n_frames)
        self._buffer = max(1, track_buffer_frames)
        self._state: dict[int, TrackState] = {}

    def step(
        self,
        *,
        frame_index: int,
        camera_id: str,
        tracks: list[Track],
    ) -> list[dict]:
        now = datetime.now(timezone.utc)
        events: list[dict] = []
        seen = {t.track_id for t in tracks}

        # enter events
        for t in tracks:
            if t.track_id not in self._state:
                self._state[t.track_id] = TrackState(last_seen_frame=frame_index)
                events.append(
                    {
                        "timestamp": now.isoformat(),
                        "camera_id": camera_id,
                        "track_id": t.track_id,
                        "event_name": "enter",
                        "x1": t.x1,
                        "y1": t.y1,
                        "x2": t.x2,
                        "y2": t.y2,
                        "cx": t.cx,
                        "cy": t.cy,
                        "confidence": t.confidence,
                        "payload": {},
                    }
                )
            else:
                self._state[t.track_id].last_seen_frame = frame_index

            if frame_index % self._pos_every == 0:
                events.append(
                    {
                        "timestamp": now.isoformat(),
                        "camera_id": camera_id,
                        "track_id": t.track_id,
                        "event_name": "position",
                        "x1": t.x1,
                        "y1": t.y1,
                        "x2": t.x2,
                        "y2": t.y2,
                        "cx": t.cx,
                        "cy": t.cy,
                        "confidence": t.confidence,
                        "payload": {},
                    }
                )

        # exit events (when unseen beyond buffer)
        for tid, st in list(self._state.items()):
            if tid in seen:
                continue
            if frame_index - st.last_seen_frame >= self._buffer:
                del self._state[tid]
                events.append(
                    {
                        "timestamp": now.isoformat(),
                        "camera_id": camera_id,
                        "track_id": tid,
                        "event_name": "exit",
                        "payload": {},
                    }
                )

        return events
