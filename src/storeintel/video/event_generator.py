from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, TypeAlias

from storeintel.video.types import Track
from storeintel.video.zone_manager import Point, Polygon, Zones, get_current_zone, load_zones


ENTRY = "entry"
EXIT = "exit"
ZONE_ENTER = "zone_enter"
ZONE_EXIT = "zone_exit"
ZONE_DWELL = "zone_dwell"


DEFAULT_OUTSIDE_ZONE = "OUTSIDE"


@dataclass(frozen=True)
class EntryLine:
    """Entry line used to classify ENTRY vs EXIT crossings.

    The line is treated as a directed segment p1->p2.

    inward_side:
      - "left": points with positive signed area are considered inside
      - "right": points with negative signed area are considered inside
    """

    p1: Point
    p2: Point
    inward_side: str = "left"

    def inside_sign(self) -> int:
        if self.inward_side not in ("left", "right"):
            raise ValueError("inward_side must be 'left' or 'right'")
        return 1 if self.inward_side == "left" else -1


@dataclass
class _TrackState:
    last_seen_frame: int
    last_point: Point | None = None
    last_zone: str | None = None
    zone_entered_at: datetime | None = None
    dwell_emitted: bool = False


JSONDict: TypeAlias = dict[str, object]


def _signed_area(p: Point, a: Point, b: Point) -> float:
    """Signed area *2 of triangle (a,b,p) == cross((b-a),(p-a))."""
    ax, ay = a
    bx, by = b
    px, py = p
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def _orientation(a: Point, b: Point, c: Point) -> int:
    val = _signed_area(c, a, b)
    if abs(val) < 1e-9:
        return 0
    return 1 if val > 0 else 2


def _on_segment(a: Point, b: Point, c: Point) -> bool:
    """Return True if point b lies on segment ac (assuming collinear)."""
    return (
        min(a[0], c[0]) - 1e-9 <= b[0] <= max(a[0], c[0]) + 1e-9
        and min(a[1], c[1]) - 1e-9 <= b[1] <= max(a[1], c[1]) + 1e-9
    )


def _segments_intersect(p1: Point, q1: Point, p2: Point, q2: Point) -> bool:
    o1 = _orientation(p1, q1, p2)
    o2 = _orientation(p1, q1, q2)
    o3 = _orientation(p2, q2, p1)
    o4 = _orientation(p2, q2, q1)

    if o1 != o2 and o3 != o4:
        return True

    # Special cases: collinear overlap
    if o1 == 0 and _on_segment(p1, p2, q1):
        return True
    if o2 == 0 and _on_segment(p1, q2, q1):
        return True
    if o3 == 0 and _on_segment(p2, p1, q2):
        return True
    if o4 == 0 and _on_segment(p2, q1, q2):
        return True

    return False


def _coerce_point(value: object) -> Point:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"Point must be [x, y], got: {value!r}")
    x, y = value
    return float(x), float(y)


def load_zone_config(zones_json_path: str | os.PathLike[str] | None = None) -> tuple[Zones, EntryLine | None]:
    """Load zones (required) and optional entry line from a JSON file.

    Uses storeintel.video.zone_manager.load_zones() for zone polygons.

    Optional entry line config supported (top-level or under "config"):

    {
      "zones": { ... },
      "entry_line": {"p1": [x,y], "p2": [x,y], "inward_side": "left"}
    }

    If no entry_line is present, returns (zones, None).
    """

    if zones_json_path is None:
        env_path = os.getenv("STOREINTEL_ZONES_PATH")
        zones_json_path = env_path or "zones.json"

    zones = load_zones(zones_json_path)

    payload = json.loads(Path(zones_json_path).read_text(encoding="utf-8"))
    entry_obj = None
    if isinstance(payload, dict):
        entry_obj = payload.get("entry_line")
        if entry_obj is None and isinstance(payload.get("config"), dict):
            entry_obj = payload["config"].get("entry_line")

    if not isinstance(entry_obj, dict):
        return zones, None

    p1 = _coerce_point(entry_obj.get("p1"))
    p2 = _coerce_point(entry_obj.get("p2"))
    inward_side = str(entry_obj.get("inward_side") or "left")
    return zones, EntryLine(p1=p1, p2=p2, inward_side=inward_side)


class EventGenerator:
    """Generates ENTRY/EXIT + zone transition and dwell events from ByteTrack tracks.

    Input:
      - tracks: list[storeintel.video.types.Track] (ByteTrack output)
      - zones: polygons loaded via zone_manager.load_zones

    Output:
      - list of event dicts (internal format), suitable for converting to JSONL via events_to_jsonl().

    Notes:
      - ENTRY/EXIT require an EntryLine. If entry_line=None, no entry/exit crossing events are produced.
      - ZONE_DWELL is emitted once per (track, zone) visit after dwell_seconds.
    """

    def __init__(
        self,
        *,
        zones: Mapping[str, Polygon],
        entry_line: EntryLine | None = None,
        dwell_seconds: float = 30.0,
        zone_default: str = DEFAULT_OUTSIDE_ZONE,
    ):
        self._zones: Zones = {str(k): list(v) for k, v in zones.items()}
        self._entry_line = entry_line
        self._zone_default = zone_default
        self._dwell = max(0.0, float(dwell_seconds))
        self._state: dict[int, _TrackState] = {}

    def step(
        self,
        *,
        frame_index: int,
        camera_id: str,
        tracks: list[Track],
        timestamp: datetime | None = None,
    ) -> list[JSONDict]:
        now = timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        events: list[JSONDict] = []

        for t in tracks:
            state = self._state.get(t.track_id)
            if state is None:
                state = _TrackState(last_seen_frame=frame_index)
                self._state[t.track_id] = state
            else:
                state.last_seen_frame = frame_index

            curr_point: Point = (t.cx, t.cy)
            curr_zone = get_current_zone(curr_point, self._zones, default=self._zone_default)

            # ENTRY/EXIT crossing detection
            if self._entry_line is not None and state.last_point is not None:
                if _segments_intersect(state.last_point, curr_point, self._entry_line.p1, self._entry_line.p2):
                    prev_area = _signed_area(state.last_point, self._entry_line.p1, self._entry_line.p2)
                    curr_area = _signed_area(curr_point, self._entry_line.p1, self._entry_line.p2)
                    if abs(prev_area) > 1e-9 and abs(curr_area) > 1e-9 and (prev_area > 0) != (curr_area > 0):
                        inside_prev = (prev_area > 0) == (self._entry_line.inside_sign() > 0)
                        inside_curr = (curr_area > 0) == (self._entry_line.inside_sign() > 0)
                        if not inside_prev and inside_curr:
                            events.append(
                                self._make_event(
                                    now=now,
                                    camera_id=camera_id,
                                    t=t,
                                    event_type=ENTRY,
                                    zone_id=curr_zone,
                                    dwell_ms=None,
                                )
                            )
                        elif inside_prev and not inside_curr:
                            events.append(
                                self._make_event(
                                    now=now,
                                    camera_id=camera_id,
                                    t=t,
                                    event_type=EXIT,
                                    zone_id=curr_zone,
                                    dwell_ms=None,
                                )
                            )

            # ZONE enter/exit
            if state.last_zone is None:
                # First observation: treat as zone enter if inside a non-default zone.
                if curr_zone != self._zone_default:
                    state.last_zone = curr_zone
                    state.zone_entered_at = now
                    state.dwell_emitted = False
                    events.append(
                        self._make_event(
                            now=now,
                            camera_id=camera_id,
                            t=t,
                            event_type=ZONE_ENTER,
                            zone_id=curr_zone,
                            dwell_ms=0,
                        )
                    )
            else:
                if curr_zone != state.last_zone:
                    # leaving previous zone
                    if state.last_zone != self._zone_default:
                        dwell_ms = None
                        if state.zone_entered_at is not None:
                            dwell_ms = max(0, int((now - state.zone_entered_at).total_seconds() * 1000))
                        events.append(
                            self._make_event(
                                now=now,
                                camera_id=camera_id,
                                t=t,
                                event_type=ZONE_EXIT,
                                zone_id=state.last_zone,
                                dwell_ms=dwell_ms,
                            )
                        )

                    # entering new zone
                    if curr_zone != self._zone_default:
                        state.zone_entered_at = now
                        state.dwell_emitted = False
                        events.append(
                            self._make_event(
                                now=now,
                                camera_id=camera_id,
                                t=t,
                                event_type=ZONE_ENTER,
                                zone_id=curr_zone,
                                dwell_ms=0,
                            )
                        )
                    else:
                        state.zone_entered_at = None
                        state.dwell_emitted = False

                    state.last_zone = curr_zone

            # ZONE dwell
            if (
                curr_zone != self._zone_default
                and state.zone_entered_at is not None
                and not state.dwell_emitted
                and (now - state.zone_entered_at) >= timedelta(seconds=self._dwell)
            ):
                dwell_ms = max(0, int((now - state.zone_entered_at).total_seconds() * 1000))
                events.append(
                    self._make_event(
                        now=now,
                        camera_id=camera_id,
                        t=t,
                        event_type=ZONE_DWELL,
                        zone_id=curr_zone,
                        dwell_ms=dwell_ms,
                    )
                )
                state.dwell_emitted = True

            state.last_point = curr_point

        return events

    def _make_event(
        self,
        *,
        now: datetime,
        camera_id: str,
        t: Track,
        event_type: str,
        zone_id: str | None,
        dwell_ms: int | None,
    ) -> JSONDict:
        return {
            "timestamp": now.isoformat(),
            "camera_id": camera_id,
            "track_id": t.track_id,
            "event_name": event_type,
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "x1": t.x1,
            "y1": t.y1,
            "x2": t.x2,
            "y2": t.y2,
            "cx": t.cx,
            "cy": t.cy,
            "confidence": t.confidence,
            "payload": {},
        }


def events_to_jsonl(
    events: Iterable[Mapping[str, object]],
    *,
    store_id: str,
    default_visitor_id: str = "unknown",
) -> Iterable[str]:
    """Convert internal event dicts to JSONL lines matching the ingestion schema.

    Produces JSON objects compatible with storeintel.schemas.events.EventIn.
    """

    for ev in events:
        track_id = ev.get("track_id")
        visitor_id = str(track_id) if track_id is not None else default_visitor_id

        payload = ev.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        obj = {
            "store_id": store_id,
            "camera_id": ev.get("camera_id"),
            "visitor_id": visitor_id,
            "event_type": ev.get("event_name"),
            "timestamp": ev.get("timestamp"),
            "zone_id": ev.get("zone_id"),
            "dwell_ms": ev.get("dwell_ms"),
            "is_staff": bool(ev.get("is_staff", False)),
            "confidence": ev.get("confidence"),
            "metadata": {
                **payload,
                "x1": ev.get("x1"),
                "y1": ev.get("y1"),
                "x2": ev.get("x2"),
                "y2": ev.get("y2"),
                "cx": ev.get("cx"),
                "cy": ev.get("cy"),
                "track_id": track_id,
            },
        }

        yield json.dumps(obj, ensure_ascii=False)


def write_jsonl(
    jsonl_path: str | os.PathLike[str],
    events: Iterable[Mapping[str, object]],
    *,
    store_id: str,
) -> None:
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for line in events_to_jsonl(events, store_id=store_id):
            f.write(line)
            f.write("\n")
