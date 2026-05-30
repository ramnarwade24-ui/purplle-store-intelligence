"""Backward-compatible module.

The project now uses SQLAlchemy ORM in `storeintel.db.database`.
This module remains to avoid breaking older imports.
"""

from __future__ import annotations

from storeintel.db.database import get_engine, init_db

__all__ = ["get_engine", "init_db"]

