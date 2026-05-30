# Data Model

## VisitorEvent

Represents a single derived event from tracking.

Core fields:

- `timestamp` (UTC)
- `camera_id`
- `track_id`
- `event_name` (`enter|position|exit|...`)
- `cx, cy` (centroid)
- `x1, y1, x2, y2` (bbox)
- `payload` (JSON)
