from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from .. import db

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz():
    session = db.SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        return {"status": "ready"}
    finally:
        session.close()
