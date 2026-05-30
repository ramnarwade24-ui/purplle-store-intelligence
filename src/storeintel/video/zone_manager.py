from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, TypeAlias


Point: TypeAlias = tuple[float, float]
Polygon: TypeAlias = list[Point]
Zones: TypeAlias = dict[str, Polygon]


ENTRY_ZONE = "ENTRY_ZONE"
FOH_ZONE = "FOH_ZONE"
BILLING_ZONE = "BILLING_ZONE"
TOP_BRANDS_ZONE = "TOP_BRANDS_ZONE"
BOTTOM_BRANDS_ZONE = "BOTTOM_BRANDS_ZONE"

REQUIRED_ZONES: tuple[str, ...] = (
    ENTRY_ZONE,
    FOH_ZONE,
    BILLING_ZONE,
    TOP_BRANDS_ZONE,
    BOTTOM_BRANDS_ZONE,
)

ZONE_PRIORITY: tuple[str, ...] = REQUIRED_ZONES


@dataclass(frozen=True)
class Zone:
    name: str
    polygon: Polygon


def _coerce_point(value: object) -> Point:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"Point must be [x, y], got: {value!r}")

    x, y = value
    try:
        return float(x), float(y)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Point coordinates must be numeric, got: {value!r}") from exc


def _coerce_polygon(value: object) -> Polygon:
    if not isinstance(value, list):
        raise ValueError(f"Polygon must be a list of points, got: {type(value).__name__}")
    polygon = [_coerce_point(p) for p in value]
    if len(polygon) < 3:
        raise ValueError(f"Polygon must have at least 3 points, got {len(polygon)}")
    return polygon


def _normalize_zones_payload(payload: object) -> Zones:
    if not isinstance(payload, dict):
        raise ValueError("Zones JSON must be an object")

    if "zones" in payload:
        zones_raw = payload["zones"]
    else:
        # Allow the simplest form: {"ENTRY_ZONE": [[x,y],...], ...}
        zones_raw = payload

    zones: Zones = {}

    if isinstance(zones_raw, dict):
        for name, poly in zones_raw.items():
            if not isinstance(name, str):
                raise ValueError("Zone names must be strings")
            zones[name] = _coerce_polygon(poly)
        return zones

    if isinstance(zones_raw, list):
        for item in zones_raw:
            if not isinstance(item, dict):
                raise ValueError("Each zone entry must be an object")
            name = item.get("name")
            polygon = item.get("polygon")
            if not isinstance(name, str) or not name:
                raise ValueError("Zone entry missing valid 'name'")
            zones[name] = _coerce_polygon(polygon)
        return zones

    raise ValueError("'zones' must be either an object or a list")


def load_zones(zones_json_path: str | os.PathLike[str] | None = None) -> Zones:
    """Load store zones from a JSON file.

    Supported JSON shapes:

    1) Object mapping:
       {
         "ENTRY_ZONE": [[x,y], ...],
         "FOH_ZONE": [[x,y], ...]
       }

    2) Wrapped mapping:
       {"zones": {"ENTRY_ZONE": [[x,y], ...], ...}}

    3) List entries:
       {"zones": [{"name": "ENTRY_ZONE", "polygon": [[x,y], ...]}, ...]}

    Path resolution order when zones_json_path is None:
    - env var STOREINTEL_ZONES_PATH
    - ./zones.json (current working directory)

    Returns a dict mapping zone name -> polygon (list of (x,y) points).
    """

    if zones_json_path is None:
        env_path = os.getenv("STOREINTEL_ZONES_PATH")
        zones_json_path = env_path or "zones.json"

    path = Path(zones_json_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Zones JSON not found at {str(path)!r}. "
            "Pass zones_json_path=..., or set STOREINTEL_ZONES_PATH."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    zones = _normalize_zones_payload(payload)

    missing = [z for z in REQUIRED_ZONES if z not in zones]
    if missing:
        raise ValueError(
            "Zones JSON missing required zones: "
            + ", ".join(missing)
            + f". Required: {', '.join(REQUIRED_ZONES)}"
        )

    return zones


def _point_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> bool:
    # Collinearity check via cross product near zero, then bounding-box check.
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > 1e-9:
        return False

    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < 0:
        return False

    squared_len = (bx - ax) * (bx - ax) + (by - ay) * (by - ay)
    if dot > squared_len:
        return False

    return True


def is_point_inside_zone(point: Point, polygon: Iterable[Point]) -> bool:
    """Return True if point lies inside (or on the edge of) the polygon."""

    px, py = float(point[0]), float(point[1])
    poly = list(polygon)
    if len(poly) < 3:
        return False

    # Edge-inclusive: if on any boundary segment, treat as inside.
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        if _point_on_segment(px, py, float(ax), float(ay), float(bx), float(by)):
            return True

    # Ray casting algorithm.
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])

        intersects = (yi > py) != (yj > py)
        if intersects:
            # Compute x-coordinate where the edge crosses the horizontal line at py.
            x_at_py = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_at_py:
                inside = not inside

        j = i

    return inside


def get_current_zone(
    centroid: Point,
    zones: Mapping[str, Polygon],
    *,
    default: str = "UNKNOWN",
    priority: Iterable[str] | None = None,
) -> str:
    """Return the zone name that contains the given centroid.

    If multiple zones contain the point, the first match by `priority` wins.
    If `priority` is None, REQUIRED_ZONES order is used first, then any extras.
    """

    ordered_names: list[str] = []

    if priority is None:
        for name in ZONE_PRIORITY:
            if name in zones:
                ordered_names.append(name)
        for name in zones.keys():
            if name not in ordered_names:
                ordered_names.append(name)
    else:
        ordered_names.extend([n for n in priority if n in zones])

    for name in ordered_names:
        if is_point_inside_zone(centroid, zones[name]):
            return name

    return default
