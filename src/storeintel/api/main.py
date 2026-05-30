from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from storeintel.api.routers import (
    anomalies,
    events,
    funnel,
    health,
    heatmap,
    ingest,
    metrics,
    store_anomalies,
    store_funnel,
    store_metrics,
)
from storeintel.core.logging import configure_logging, get_logger, request_id_ctx
from storeintel.core.settings import get_settings
from storeintel.db.database import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    log = get_logger(__name__)
    init_db(settings.sqlite_path)

    app = FastAPI(title="Store Intelligence API", version="0.1.0")

    @app.middleware("http")
    async def request_context_middleware(request, call_next):
        rid = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        if rid:
            response.headers["x-request-id"] = rid
        return response

    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(store_metrics.router)
    app.include_router(store_funnel.router)
    app.include_router(store_anomalies.router)
    app.include_router(events.router, prefix="/v1")
    app.include_router(metrics.router, prefix="/v1")
    app.include_router(funnel.router, prefix="/v1")
    app.include_router(heatmap.router, prefix="/v1")
    app.include_router(anomalies.router, prefix="/v1")

    log.info("api_started", host=settings.api_host, port=settings.api_port)
    return app


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "storeintel.api.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
    )
