# Store Intelligence System — Design

## 1. Problem Statement

Retail stores frequently lack objective, near-real-time visibility into how customers move through the floor, where engagement occurs, when queues form, and where conversion drops happen. Existing signals (POS transactions, manual counts, periodic audits) are typically delayed, fragmented, and do not connect customer journey stages (entry → zone visits → billing → purchase) in a unified operational view.

The Store Intelligence System addresses this by converting CCTV video into structured, privacy-conscious visitor events and then aggregating those events into actionable operational metrics and anomaly findings. The system is designed to:

- Detect and track people in video streams.
- Generate consistent, time-stamped events (movement, zone transitions, dwell) with stable visitor identifiers.
- Ingest and store events reliably.
- Provide analytics APIs and a dashboard for decision makers.
- Produce anomaly findings with suggested actions for store operations.

## 2. System Architecture

The implementation follows a three-service architecture with a shared data contract (event schema) and a single source of truth for analytics (SQLite in the current deployment).

- **Processor** (`storeintel.processor`): Batch processing of video → detection + tracking → event generation → HTTP ingestion.
- **API** (`storeintel.api`): FastAPI service that ingests events into SQLite and exposes query + analytics endpoints.
- **Dashboard** (`apps/dashboard`): Streamlit UI that consumes API endpoints and visualizes key metrics.

Primary data flow:

```mermaid
flowchart LR
  V[Video File / CCTV Stream] --> P[Processor
YOLOv8 + ByteTrack]
  P --> E[Visitor Events
(JSON batch)]
  E -->|POST| A[FastAPI API]
  A --> D[(SQLite DB)]
  D --> A
  A -->|GET Metrics/Funnel/Anomalies| S[Streamlit Dashboard]
```

Operational characteristics:

- The Processor is compute-heavy (CV + tracking) and is intentionally decoupled from the API so it can scale independently.
- The API is optimized for correctness and simplicity: validate → persist → query.
- The Dashboard is a read-only consumer and can be scaled separately.

## 3. Detection Pipeline

The detection stage transforms raw frames into candidate person detections.

1. **Frame acquisition**
   - Video frames are read using OpenCV (`cv2.VideoCapture`).
   - A configurable **frame stride** reduces compute load by skipping frames (defaults are defined in configuration).

2. **People detection (YOLOv8)**
   - The detector runs a YOLOv8 model (e.g., `yolov8n.pt`) and filters for people.
   - A configurable confidence threshold controls the precision/recall tradeoff.

3. **Detection output contract**
   - Each detection includes bounding box coordinates (`x1, y1, x2, y2`), centroid (`cx, cy`), and optional confidence.
   - Only the minimal geometry needed for tracking and zone mapping is retained.

Design rationale:

- Frame stride and confidence threshold provide inexpensive levers to tune throughput.
- Keeping detection output small limits payload size and reduces downstream storage cost.

## 4. Event Generation Pipeline

The event generation stage converts short-lived detections into stable, higher-level events that are meaningful for analytics.

1. **Multi-object tracking (ByteTrack)**
   - ByteTrack is used to associate detections across frames and assign stable `track_id` values.
   - A configurable track buffer smooths intermittent occlusions and missed detections.

2. **Per-track state management**
   - The system maintains a state machine per `track_id` (last seen frame, previous centroid, last known zone, and dwell timing).
   - State is used to infer discrete transitions (e.g., zone entry/exit) and to prevent repeated emission of dwell events.

3. **Zones and entry/exit semantics**
   - Zones are polygons loaded from a JSON configuration file (default `zones.json`, overrideable via environment variable).
   - An optional **directed entry line** can be configured to classify crossings as `entry` vs `exit` based on side-of-line changes.
   - A default “outside” zone is used when a centroid does not fall within a configured zone.

4. **Event types**
   The event generator can emit:

   - `entry` / `exit` (when an entry line is configured)
   - `zone_enter` / `zone_exit`
   - `zone_dwell` (emitted once per (visitor, zone) visit after a dwell threshold)

5. **Event enrichment**
   - Events are enriched with geometry (bbox + centroid), zone id, and a stable visitor identifier.
   - The Processor maps `track_id` → `visitor_id` for downstream storage and analytics.

Design rationale:

- Analytics depends on stable identities and discrete transitions; tracking + state machines provide these primitives.
- Zone-based modeling aligns to retail operations (front-of-house, top brands, billing/checkout).

## 5. Database Design

SQLite is used as the operational database in the current deployment for fast iteration and a low-ops footprint. SQLAlchemy models define the schema and indices.

Core tables:

- **stores**
  - `store_id` primary key and optional store metadata.

- **events** (primary fact table)
  - Identifiers: `event_id` (UUID string), `store_id`, `camera_id`, `visitor_id`
  - Measures/dimensions: `event_type`, `timestamp`, `zone_id`, `dwell_ms`, `is_staff`, `confidence`
  - `payload` (JSON): free-form metadata including bbox/centroid and correlation fields (e.g., `track_id`).

- **visitor_sessions**
  - Supports sessionization semantics (entry/exit windows) and derived rollups.

- **purchases**
  - Stores POS transaction facts and enables conversion attribution.

- **anomalies**
  - Stores anomaly detections (bucketed metrics, scores, and metadata).

Indexes are applied to support the dominant query patterns:

- Time-series queries by `(store_id, camera_id, timestamp)`
- Filtering by `event_type`, `zone_id`, and `visitor_id`

Design rationale:

- Events are treated as an append-oriented fact stream; JSON metadata keeps the base schema stable while allowing iteration.
- SQLite is sufficient for single-node demos and small stores; the schema is portable to Postgres with minimal changes.

## 6. API Design

The API is a FastAPI service that provides ingestion, health reporting, and read APIs for analytics.

### Health

- `GET /healthz`
  - Liveness response (`{"status":"ok"}`) for simple uptime checks.

- `GET /health`
  - Readiness-style response; includes database status and last event timestamp.

### Ingestion

Two ingestion paths exist:

- `POST /v1/events`
  - Accepts `List[EventIn]` (strict, request fails if schema validation fails).
  - Returns `{ "inserted": N }`.

- `POST /events/ingest`
  - Batch ingestion endpoint with partial success support.
  - Per-item validation, within-batch de-duplication on `event_id`, and de-duplication against existing rows.
  - Enforces a maximum batch size (500).
  - Returns `{ "accepted": A, "duplicates": D, "failed": F }`.

Event schema principles:

- `timestamp` must be timezone-aware.
- `event_id` is optional and can be supplied by clients for idempotency.
- `metadata` is the preferred free-form field; legacy clients may send `payload` (accepted as an alias).

### Query and Analytics

- `GET /v1/events`
  - Filter by `start`, `end`, `camera_id`, and `limit`.

- Generic analytics (camera/time scoped):
  - `GET /v1/metrics/visitors`
  - `GET /v1/funnel`
  - `GET /v1/heatmap`
  - `GET /v1/anomalies`

- Store-focused analytics (store id scoped):
  - `GET /stores/{store_id}/metrics`
  - `GET /stores/{store_id}/funnel`
  - `GET /stores/{store_id}/anomalies`

Design rationale:

- Ingestion endpoints separate “developer simplicity” (`/v1/events`) from “production robustness” (`/events/ingest`).
- Store-scoped endpoints represent the dashboard’s primary consumption model.

## 7. Dashboard Design

The dashboard is implemented as a Streamlit application that consumes API endpoints and presents an operational view suitable for store managers and analysts.

Key design elements:

- **Connectivity model**
  - The API base URL is configurable via `API_BASE_URL` environment variable.
  - The UI also allows editing the base URL in the sidebar for flexible deployments.

- **Auto-refresh**
  - The dashboard refreshes periodically (default 5s) to approximate real-time monitoring without requiring push infrastructure.

- **Core views**
  - KPI tiles: unique visitors, conversion rate, queue depth.
  - Funnel visualization: entry → zone visit → billing → purchase.
  - Active anomalies list: type, severity, description, suggested action.
  - Zone heatmap: aggregated zone activity over a time window.

Design rationale:

- Streamlit provides a fast path to a credible UI with minimal backend coupling.
- Pull-based refresh keeps infrastructure simple while still delivering operational value.

## 8. Scalability Considerations

The current implementation is optimized for clarity and correctness on a single node. Scaling paths are intentionally straightforward.

1. **Compute scaling (Processor)**
   - Run one processor per camera/stream or per video shard.
   - Use GPU-backed nodes for YOLO inference when throughput becomes the bottleneck.

2. **Ingestion scaling (API)**
   - Introduce an ingestion queue (e.g., Kafka, Azure Service Bus, RabbitMQ) and make the API an asynchronous consumer.
   - Batch writes and use write-optimized storage.

3. **Storage scaling**
   - Move from SQLite to Postgres for concurrency and operational durability.
   - Consider time partitioning (by day/week) and indexing strategies for event-heavy stores.

4. **Query scaling**
   - Pre-aggregate metrics (hourly/daily rollups) and cache common dashboard queries.
   - Offload analytics to a warehouse for long-range trend analysis.

5. **Multi-tenancy and isolation**
   - Enforce store-level authorization and data isolation.
   - Separate per-store storage or apply row-level security when migrating to a multi-tenant database.

## 9. AI Assisted Decisions

The system already includes “AI-assisted” operational decision support via deterministic analytics that produce human-actionable recommendations.

Current capabilities:

- **Anomaly detection engine**
  - Detects operational anomalies such as queue spikes, conversion drops, and dead zones using recent-vs-baseline comparisons.
  - Emits suggested actions (e.g., open additional checkout lane, investigate POS slowdown).

- **Conversion attribution support**
  - Correlates POS transactions to visitors using a time-window heuristic around billing-zone entry.

Near-term enhancements (still interpretable, ops-friendly):

- Learn per-store baselines (day-of-week/hour-of-day seasonality) to reduce false positives.
- Train lightweight predictive models for queue formation risk and expected conversion.
- Improve staff vs customer classification using appearance/trajectory heuristics and optional staff badge/ROI constraints.

Longer-term “assistive intelligence”:

- Generate incident summaries and recommended playbooks (e.g., “queue spike likely due to staffing; ETA 15 minutes”) for managers.
- Incorporate feedback loops: accept/ignore anomaly, action taken, and outcome → improve thresholds/models.

## 10. Future Improvements

- **Real-time streaming**: Replace pull refresh with server-push (WebSocket/SSE) and event streaming ingestion.
- **Better calibration**: Camera calibration and homography to convert pixel coordinates into store-map coordinates.
- **Zone configuration UX**: Admin UI for drawing polygons/entry lines and validating zone coverage.
- **Robust identity**: Re-identification across cameras (multi-camera tracking) and stronger visitor/session modeling.
- **Observability**: Structured traces/metrics, SLOs, and alerting on ingestion lag and anomaly rates.
- **Security & governance**: Authentication/authorization, audit logging, and PII minimization policies.
- **Data lifecycle**: Retention policies, compaction, and rollups for long-term storage efficiency.
- **Testing & quality**: Golden video fixtures, deterministic replay tests for event generation, and contract tests for ingestion.
