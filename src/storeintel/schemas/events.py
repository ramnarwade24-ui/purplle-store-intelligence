from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


_EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*$"


class EventIn(BaseModel):
    """Incoming event payload.

    Accepts both `metadata` (preferred) and legacy `payload`.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    event_id: UUID | None = Field(
        default=None,
        description="Optional client-supplied UUID for idempotency; server generates one if omitted.",
    )

    store_id: str = Field(..., min_length=1, max_length=64)
    camera_id: str = Field(..., min_length=1, max_length=128)
    visitor_id: str = Field(..., min_length=1, max_length=128)

    event_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=_EVENT_TYPE_PATTERN,
        description="Lowercase identifier (e.g., enter|exit|position).",
    )
    timestamp: datetime

    zone_id: str | None = Field(default=None, min_length=1, max_length=128)
    dwell_ms: int | None = Field(default=None, ge=0)
    is_staff: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata", "payload"),
        description="Free-form JSON metadata (accepted from legacy 'payload').",
    )

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("timestamp must be timezone-aware")
        return v


class EventOut(EventIn):
    event_id: UUID
