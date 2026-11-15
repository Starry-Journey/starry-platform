from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytz
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..astrology import (
    compute_chart as default_compute_chart,
)
from ..astrology import (
    compute_synastry as default_compute_synastry,
)
from ..astrology import (
    compute_transits as default_compute_transits,
)
from ..config import settings
from ..db import get_db
from ..models import Chart, User
from ..reading import generate_reading as default_generate_reading
from ..schemas import ChartIn, ChartOut, ChartSummary, SynastryIn, TransitIn
from ..security import current_user

router = APIRouter(prefix="/v1/charts", tags=["charts"])

compute_chart = default_compute_chart
generate_reading = default_generate_reading
compute_transits = default_compute_transits
compute_synastry = default_compute_synastry


def _fernet() -> Fernet:
    if not settings.chart_enc_key:
        raise HTTPException(status_code=503, detail="星盘加密密钥未配置")
    try:
        return Fernet(settings.chart_enc_key.encode())
    except Exception:
        raise HTTPException(status_code=503, detail="星盘加密密钥无效")


@router.post("", response_model=ChartOut, status_code=201)
def create_chart(
    payload: ChartIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        tz = pytz.timezone(payload.timezone)
    except pytz.UnknownTimeZoneError:
        raise HTTPException(status_code=422, detail="时区无效")

    try:
        naive = datetime.strptime(f"{payload.birth_date} {payload.birth_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=422, detail="出生时间格式应为 YYYY-MM-DD HH:MM")

    local = tz.localize(naive)
    utc = local.astimezone(timezone.utc)

    chart = compute_chart(utc, payload.latitude, payload.longitude, payload.house_system)

    birth = {
        "date": payload.birth_date,
        "time": payload.birth_time,
        "timezone": payload.timezone,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
    }
    encrypted = _fernet().encrypt(json.dumps(birth, ensure_ascii=False).encode()).decode()

    record = Chart(
        user_id=user.id,
        label=payload.label,
        encrypted_birth=encrypted,
        chart_json=json.dumps(chart, ensure_ascii=False),
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "label": record.label,
        **chart,
        "created_at": record.created_at,
    }


def _owned(db: Session, chart_id: int, user: User) -> Chart:
    record = db.get(Chart, chart_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="星盘不存在")
    return record


@router.post("/synastry")
def synastry(
    payload: SynastryIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    a = _owned(db, payload.a_id, user)
    b = _owned(db, payload.b_id, user)
    if a.id == b.id:
        raise HTTPException(status_code=422, detail="请选择两张不同的星盘")
    result = compute_synastry(json.loads(a.chart_json), json.loads(b.chart_json))
    return {
        "a_id": a.id,
        "a_label": a.label or "未命名星盘",
        "b_id": b.id,
        "b_label": b.label or "未命名星盘",
        **result,
    }


@router.get("", response_model=List[ChartSummary])
def list_charts(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Chart).where(Chart.user_id == user.id).order_by(Chart.created_at.desc()).limit(50)
    ).all()
    return [{"id": r.id, "label": r.label or "未命名星盘", "created_at": r.created_at} for r in rows]


@router.post("/{chart_id}/transits")
def transits(
    chart_id: int,
    payload: TransitIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    record = _owned(db, chart_id, user)
    if payload.at:
        try:
            when = datetime.fromisoformat(payload.at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="时间格式应为 ISO 8601")
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when = when.astimezone(timezone.utc)
    else:
        when = datetime.now(timezone.utc)
    result = compute_transits(json.loads(record.chart_json), when)
    return {"chart_id": record.id, "label": record.label or "未命名星盘", **result}


@router.get("/{chart_id}", response_model=ChartOut)
def get_chart(
    chart_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    record = _owned(db, chart_id, user)
    data: Dict[str, Any] = json.loads(record.chart_json)
    return {
        "id": record.id,
        "label": record.label,
        "reading": record.reading,
        **data,
        "created_at": record.created_at,
    }


@router.post("/{chart_id}/reading")
async def read_chart(
    chart_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    record = _owned(db, chart_id, user)
    if record.reading:
        return {"reading": record.reading, "cached": True}
    chart = json.loads(record.chart_json)
    text = await generate_reading(chart)
    record.reading = text
    db.commit()
    return {"reading": text, "cached": False}


@router.delete("/{chart_id}", status_code=204)
def delete_chart(
    chart_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    record = _owned(db, chart_id, user)
    db.delete(record)
    db.commit()
    return None
