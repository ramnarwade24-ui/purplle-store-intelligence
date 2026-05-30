from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from storeintel.db.models import Event


def compute_heatmap_grid(
    events: Iterable[Event],
    *,
    width: int,
    height: int,
    grid_w: int = 64,
    grid_h: int = 36,
) -> list[list[int]]:
    grid = np.zeros((grid_h, grid_w), dtype=np.int32)
    for e in events:
        cx = e.payload.get("cx") if isinstance(e.payload, dict) else None
        cy = e.payload.get("cy") if isinstance(e.payload, dict) else None
        if cx is None or cy is None:
            continue
        # Normalize into grid
        gx = int(np.clip((float(cx) / max(width, 1)) * grid_w, 0, grid_w - 1))
        gy = int(np.clip((float(cy) / max(height, 1)) * grid_h, 0, grid_h - 1))
        grid[gy, gx] += 1
    return grid.tolist()
