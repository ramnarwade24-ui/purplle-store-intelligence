# Architecture & Technology Choices

This document records the major engineering decisions for the Store Intelligence System, including alternatives, an “AI recommendation” (i.e., a constraint-driven recommendation an engineering decision assistant would make), the final decision reflected in this repository, and the tradeoffs.

---

## Decision 1 — YOLOv8 vs RT-DETR vs YOLOv9

### Alternatives considered

- **YOLOv8** (Ultralytics)
  - Strong ecosystem, broadly adopted for real-world detection pipelines.
  - Practical model options (nano/small/medium/large) and easy CPU/GPU deployment.

- **RT-DETR**
  - Transformer-based real-time detector with competitive quality.
  - Often better global reasoning, can be strong for crowded scenes.

- **YOLOv9**
  - Newer generation with reported accuracy gains.
  - Ecosystem maturity and deployment patterns vary depending on implementation.

### AI recommendations

Given the project goals (production-grade starter, fast iteration, straightforward containerization, and a detector that “just works” across many environments), an AI decision assistant would recommend:

- Choose **YOLOv8** for the baseline because it minimizes integration risk, has a large community footprint, and provides stable inference tooling.
- Keep the architecture modular (detector interface) so that RT-DETR or a newer YOLO variant can be swapped in if accuracy/latency requirements evolve.

### Final decision

- **YOLOv8** is used for person detection (see the video detector module in the codebase).

### Tradeoffs

- **Pros**:
  - Low integration friction; well-known deployment behavior.
  - Easy to tune with model size + confidence threshold.
  - Good balance of speed and accuracy for a starter system.

- **Cons**:
  - RT-DETR may outperform in some crowded or complex scenes.
  - YOLOv9 (or other newer models) may offer better accuracy/efficiency, but may require more careful benchmarking and deployment validation.

---

## Decision 2 — ByteTrack vs DeepSORT

### Alternatives considered

- **ByteTrack**
  - Tracking-by-detection approach that associates detections with tracks using motion and association heuristics.
  - Strong practical performance with modern detectors; typically lightweight and fast.

- **DeepSORT**
  - Adds appearance embeddings (re-identification features) to improve association, especially under occlusion.
  - Often more robust when detections are intermittent or there are many similar targets.

### AI recommendations

Given constraints typical for an MVP/technical challenge (speed, simplicity, minimal extra ML components, and stable IDs within a single camera feed), an AI assistant would recommend:

- Use **ByteTrack** as the default tracker because it is fast, reliable for single-camera tracking, and avoids managing an additional embedding model.
- Consider DeepSORT only if the environment shows persistent ID switches or severe occlusion where appearance cues become essential.

### Final decision

- **ByteTrack** is used as the tracker.

### Tradeoffs

- **Pros**:
  - Lower compute cost than an appearance-based tracker.
  - Fewer moving parts (no separate embedding model, fewer dependencies).
  - Well-suited for single-camera “visitor session” style analytics.

- **Cons**:
  - More susceptible to ID switches in dense crowds or frequent occlusions.
  - DeepSORT can provide higher identity stability in difficult scenes, at the cost of extra compute/complexity.

---

## Decision 3 — SQLite vs PostgreSQL

### Alternatives considered

- **SQLite**
  - File-based database, simple operational footprint.
  - Excellent for demos, local development, and low-to-moderate write concurrency.

- **PostgreSQL**
  - Full-featured relational DB with better concurrency, durability features, and scaling patterns.
  - Strong ecosystem for analytics extensions, partitioning, and operational tooling.

### AI recommendations

For a “production-grade starter” with minimal ops and predictable deployment, an AI assistant would recommend:

- Start with **SQLite** to keep setup friction low and make the system runnable with a single `docker compose up`.
- Design the persistence layer so migration to Postgres is straightforward once concurrency, retention, or multi-tenant needs appear.

### Final decision

- **SQLite** is used as the operational datastore.
  - The Docker Compose setup mounts a persistent volume and points the API to a DB file under `/data`.

### Tradeoffs

- **Pros**:
  - Very low operational complexity.
  - Great for local development and lightweight deployments.
  - Easy backup/restore (copy a file) and deterministic demos.

- **Cons**:
  - Limited write concurrency relative to Postgres.
  - Long-term storage + high ingestion rates will require careful tuning or a move to Postgres/streaming ingestion.
  - Multi-service scaling patterns (multiple API replicas writing concurrently) are constrained.

---

## Decision 4 — Zone-based event architecture

### Alternatives considered

- **Zone-based events (chosen)**
  - Define store zones as polygons (e.g., ENTRY, FOH, BILLING).
  - Generate events when visitors enter/exit zones and when they dwell.

- **Pure trajectory storage**
  - Store raw positions at a fixed cadence and compute everything later.
  - Powerful for offline analytics but produces large volumes and requires more compute downstream.

- **Pixel-grid heatmap-first**
  - Aggregate occupancy directly into grids per time bucket.
  - Efficient for heatmaps but loses per-visitor journey semantics unless combined with tracking/sessionization.

### AI recommendations

Given the need for actionable retail analytics (funnel stages, queue depth, anomaly detection) with explainable signals and low storage cost, an AI assistant would recommend:

- Use a **zone-based event model** as the primary contract because it maps directly to operations (“customers in billing zone”, “dead zone”, “dwell in top brands”).
- Preserve just enough geometry in event metadata (bbox/centroid) to allow heatmaps and debugging without persisting every frame.

### Final decision

- The system uses **zones + event types** (`zone_enter`, `zone_exit`, `zone_dwell`, and optionally `entry`/`exit` via an entry line).

### Tradeoffs

- **Pros**:
  - Strong alignment with business semantics and dashboards.
  - Storage efficient compared to raw trajectory logs.
  - Easier to build funnels and operational alerts.

- **Cons**:
  - Depends on correct zone configuration and camera viewpoint.
  - Coarse granularity may miss subtle behaviors that require higher-frequency trajectory data.
  - Zone definitions can drift when camera placement changes; requires calibration/governance.

---

## Decision 5 — FastAPI architecture

### Alternatives considered

- **FastAPI (chosen)**
  - Python-native, type-hinted request/response models, automatic OpenAPI docs.
  - Strong fit for ingestion + analytics APIs.

- **Flask**
  - Lightweight and widely used but requires more manual work for schema validation and async patterns.

- **Django / Django REST Framework**
  - Full-stack batteries-included; heavier for a service-oriented ingestion/analytics API.

- **gRPC**
  - High performance, strong contracts, good for internal service-to-service calls.
  - Adds client complexity and is less convenient for a browser-facing dashboard and simple HTTP ingestion.

### AI recommendations

Given the need for:

- strict schema validation for event ingestion,
- clear API contracts for a dashboard,
- low-friction developer experience,

an AI assistant would recommend **FastAPI** as the best default.

It would also recommend separating concerns:

- ingestion endpoints that optimize for robustness (batch validation, dedupe, partial success),
- query/analytics endpoints that optimize for readability and operational usefulness.

### Final decision

- The API is implemented in **FastAPI** with:
  - health endpoints,
  - event ingestion endpoints,
  - analytics endpoints for metrics/funnel/heatmap/anomalies,
  - SQLAlchemy-backed persistence.

### Tradeoffs

- **Pros**:
  - Strong data validation via Pydantic.
  - Excellent developer velocity and automatic API documentation.
  - Clear separation of router modules and dependency injection patterns.

- **Cons**:
  - For very high ingestion rates, a queue + async consumers and/or gRPC may be more efficient.
  - Python performance is generally sufficient here, but heavy analytics may warrant background jobs, caching, or moving computation to a warehouse.
