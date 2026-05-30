# Architecture

## Components

- **Processor**: reads CCTV, runs detection+tracking, generates events, posts to API.
- **API**: ingests events, stores in SQLite, exposes analytics APIs.
- **Dashboard**: reads analytics APIs and visualizes key insights.

## Data Flow

1. Video frames -> YOLOv8 detections (people)
2. Detections -> ByteTrack tracks (stable IDs)
3. Tracks -> events (`enter`, periodic `position`, `exit`)
4. Events -> POST `/v1/events`
5. SQLite -> analytics queries -> REST APIs -> dashboard
