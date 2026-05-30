from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for the simplified challenge schema."""


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    store_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    camera_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    visitor_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

    zone_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class Purchase(Base):
    __tablename__ = "purchases"

    purchase_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    visitor_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    purchase_amount: Mapped[float] = mapped_column(Float, nullable=False)
    purchase_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_utcnow, nullable=False)


class VisitorSession(Base):
    __tablename__ = "visitor_sessions"

    # As specified: visitor_id + entry/exit/duration. This schema implies one active session row per visitor.
    visitor_id: Mapped[str] = mapped_column(String(128), primary_key=True)

    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)

    # Store in seconds as an integer (can be derived, but stored for convenience).
    session_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
