# API

All endpoints are JSON.

## Health

- `GET /healthz`

## Ingestion

- `POST /v1/events` (bulk)
- `GET /v1/events` (query)

## Analytics

- `GET /v1/metrics/visitors`
- `GET /v1/funnel`
- `GET /v1/heatmap`
- `GET /v1/anomalies`

Notes:

- Use `start`/`end` ISO timestamps to filter.
- Use `camera_id` to scope by camera.
