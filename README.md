# Store Intelligence System

Production-grade starter for a Store Intelligence System:

- CCTV processing (OpenCV)
- People detection (YOLOv8)
- Tracking (ByteTrack)
- Visitor event generation
- Event ingestion (FastAPI)
- Storage (SQLite)
- Analytics (metrics, funnels, heatmaps, anomalies)
- Dashboard (Streamlit)
- Structured logging (JSON)
- Containerized with Docker Compose

## Quickstart (Docker)

1) Copy env file:

```bash
cp .env.example .env
```

2) Start services:

```bash
docker compose up --build
```

Endpoints:

- API: http://localhost:8000 (docs at /docs)
- Dashboard: http://localhost:8501

## Local dev (Windows)

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements\dev.txt
.venv\Scripts\python -m storeintel.api
```

Run processor (example):

```bat
.venv\Scripts\python -m storeintel.processor --video data\sample.mp4 --camera-id cam-01
```

Run dashboard:

```bat
.venv\Scripts\streamlit run apps\dashboard\app.py
```

Run tests:

```bat
.venv\Scripts\pytest -q
```

## Architecture (high level)

- `storeintel.api`: FastAPI ingestion + query APIs
- `storeintel.processor`: CCTV video to events -> POST to API
- `storeintel.analytics`: metrics, funnels, heatmaps, anomalies computed from stored events
- `apps/dashboard`: Streamlit UI consuming API endpoints
=======
# purplle-store-intelligence
AI-powered Store Intelligence System for Purplle Tech Challenge 2026
## Dashboard

![Dashboard](docs/screenshots/dashboard.png)

## API Documentation

![Swagger](docs/screenshots/swagger.png)

## Zone Heatmap

![Heatmap](docs/screenshots/heatmap.png)

## Health Monitoring

![Health](docs/screenshots/health.png)
