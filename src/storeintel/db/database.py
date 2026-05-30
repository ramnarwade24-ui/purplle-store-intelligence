from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storeintel.db.models import Base


@lru_cache(maxsize=8)
def get_engine(sqlite_path: str) -> Engine:
    connect_args = {"check_same_thread": False}
    return create_engine(
        f"sqlite+pysqlite:///{sqlite_path}",
        echo=False,
        future=True,
        connect_args=connect_args,
    )


@lru_cache(maxsize=8)
def get_sessionmaker(sqlite_path: str):
    engine = get_engine(sqlite_path)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False, future=True)


def init_db(sqlite_path: str) -> None:
    engine = get_engine(sqlite_path)
    Base.metadata.create_all(engine)