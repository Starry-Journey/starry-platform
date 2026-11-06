from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None


def configure(url: str) -> None:
    global engine, SessionLocal
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from sqlalchemy import inspect, text

    from . import models  # noqa: F401  确保模型注册

    Base.metadata.create_all(bind=engine)
    # 轻量迁移：老库补 charts.label
    insp = inspect(engine)
    if "charts" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("charts")}
        if "label" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE charts ADD COLUMN label VARCHAR(80) DEFAULT ''"))
        if "reading" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE charts ADD COLUMN reading TEXT DEFAULT ''"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
