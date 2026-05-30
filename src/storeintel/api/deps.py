from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from storeintel.core.settings import Settings, get_settings
from storeintel.db.database import get_sessionmaker


def settings_dep() -> Settings:
    return get_settings()


def session_dep(settings: Settings = Depends(settings_dep)) -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker(settings.sqlite_path)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
