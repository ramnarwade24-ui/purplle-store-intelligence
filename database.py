from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base


@lru_cache(maxsize=8)
def get_engine(sqlite_path: str) -> Engine:
    """Create (or reuse) a SQLAlchemy engine for SQLite."""

    path = Path(sqlite_path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False}
    return create_engine(
        f"sqlite+pysqlite:///{path}",
        echo=False,
        future=True,
        connect_args=connect_args,
    )


@lru_cache(maxsize=8)
def get_sessionmaker(sqlite_path: str):
    """Return a configured SQLAlchemy Session factory."""

    engine = get_engine(sqlite_path)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False, future=True)


def init_db(sqlite_path: str) -> None:
    """Create all tables for the simplified challenge schema."""

    engine = get_engine(sqlite_path)
    Base.metadata.create_all(engine)
