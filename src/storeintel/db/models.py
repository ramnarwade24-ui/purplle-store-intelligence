from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class Store(Base):
    __tablename__ = "stores"

    store_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    events: Mapped[list[Event]] = relationship(back_populates="store", cascade="all, delete-orphan")
    visitor_sessions: Mapped[list[VisitorSession]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )
    anomalies: Mapped[list[Anomaly]] = relationship(back_populates="store", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id", ondelete="CASCADE"), index=True)
    camera_id: Mapped[str] = mapped_column(String(128), index=True)
    visitor_id: Mapped[str] = mapped_column(String(128), index=True)

    event_type: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    zone_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    store: Mapped[Store] = relationship(back_populates="events")


Index("ix_events_store_camera_time", Event.store_id, Event.camera_id, Event.timestamp)


class Purchase(Base):
    __tablename__ = "purchases"

    purchase_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    visitor_id: Mapped[str] = mapped_column(String(128), index=True)
    transaction_id: Mapped[str] = mapped_column(String(128), index=True, unique=True)

    purchase_amount: Mapped[float] = mapped_column(Float)
    purchase_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


Index("ix_purchases_visitor_time", Purchase.visitor_id, Purchase.purchase_timestamp)


class VisitorSession(Base):
    __tablename__ = "visitor_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id", ondelete="CASCADE"), index=True)
    camera_id: Mapped[str] = mapped_column(String(128), index=True)
    visitor_id: Mapped[str] = mapped_column(String(128), index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_staff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    store: Mapped[Store] = relationship(back_populates="visitor_sessions")


Index(
    "ix_sessions_store_visitor_started",
    VisitorSession.store_id,
    VisitorSession.visitor_id,
    VisitorSession.started_at,
)


class Anomaly(Base):
    __tablename__ = "anomalies"

    anomaly_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id", ondelete="CASCADE"), index=True)
    camera_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    zone_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    metric_name: Mapped[str] = mapped_column(String(128), index=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    value: Mapped[float] = mapped_column(Float)
    zscore: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    store: Mapped[Store] = relationship(back_populates="anomalies")


Index("ix_anomalies_store_metric_bucket", Anomaly.store_id, Anomaly.metric_name, Anomaly.bucket_start)
