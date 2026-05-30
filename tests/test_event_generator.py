from __future__ import annotations

from datetime import datetime, timedelta, timezone

from storeintel.video.event_generator import (
    ENTRY,
    EXIT,
    ZONE_DWELL,
    ZONE_ENTER,
    ZONE_EXIT,
    EntryLine,
    EventGenerator,
)
from storeintel.video.types import Track


def _track(track_id: int, cx: float, cy: float) -> Track:
    # Build a tiny bbox around centroid so cx/cy are stable.
    return Track(track_id=track_id, x1=cx - 1, y1=cy - 1, x2=cx + 1, y2=cy + 1, confidence=0.9)


def test_entry_exit_zone_and_dwell_events() -> None:
    # FOH_ZONE: square in x in [0, 10], y in [0, 10]
    zones = {
        # Keep required zones present, but place ENTRY_ZONE away from our test points.
        "ENTRY_ZONE": [(-110.0, -110.0), (-100.0, -110.0), (-100.0, -100.0), (-110.0, -100.0)],
        "FOH_ZONE": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        "BILLING_ZONE": [(100.0, 0.0), (110.0, 0.0), (110.0, 10.0), (100.0, 10.0)],
        "TOP_BRANDS_ZONE": [(0.0, 100.0), (10.0, 100.0), (10.0, 110.0), (0.0, 110.0)],
        "BOTTOM_BRANDS_ZONE": [(0.0, -110.0), (10.0, -110.0), (10.0, -100.0), (0.0, -100.0)],
    }

    # Entry line is the y-axis segment from y=0..10.
    # Directed upward; "right" side corresponds to x>0.
    entry_line = EntryLine(p1=(0.0, 0.0), p2=(0.0, 10.0), inward_side="right")

    gen = EventGenerator(zones=zones, entry_line=entry_line, dwell_seconds=30.0, zone_default="OUTSIDE")

    cam = "cam-01"
    t0 = datetime(2026, 5, 30, 0, 0, 0, tzinfo=timezone.utc)

    # First frame: outside left of entry line.
    evs = gen.step(frame_index=0, camera_id=cam, tracks=[_track(1, -1.0, 5.0)], timestamp=t0)
    assert evs == []

    # Cross entry line inward into FOH_ZONE.
    evs = gen.step(frame_index=1, camera_id=cam, tracks=[_track(1, 1.0, 5.0)], timestamp=t0 + timedelta(seconds=1))
    names = [e["event_name"] for e in evs]
    assert ENTRY in names
    assert ZONE_ENTER in names

    # Stay inside for 31 seconds total -> dwell fires once.
    evs = gen.step(
        frame_index=2,
        camera_id=cam,
        tracks=[_track(1, 2.0, 5.0)],
        timestamp=t0 + timedelta(seconds=31),
    )
    names = [e["event_name"] for e in evs]
    assert ZONE_DWELL in names

    # Another step inside should not emit dwell again.
    evs = gen.step(
        frame_index=3,
        camera_id=cam,
        tracks=[_track(1, 3.0, 5.0)],
        timestamp=t0 + timedelta(seconds=35),
    )
    assert all(e["event_name"] != ZONE_DWELL for e in evs)

    # Exit FOH zone to the right (still inside the entry side, so no EXIT event).
    evs = gen.step(
        frame_index=4,
        camera_id=cam,
        tracks=[_track(1, 20.0, 5.0)],
        timestamp=t0 + timedelta(seconds=36),
    )
    names = [e["event_name"] for e in evs]
    assert ZONE_EXIT in names

    # Cross entry line outward (right -> left) triggers EXIT.
    evs = gen.step(
        frame_index=5,
        camera_id=cam,
        tracks=[_track(1, -1.0, 5.0)],
        timestamp=t0 + timedelta(seconds=37),
    )
    names = [e["event_name"] for e in evs]
    assert EXIT in names
