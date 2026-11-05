from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytz
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..astrology import compute_chart as default_compute_chart
from ..config import settings
from ..db import get_db
from ..models import Chart, User
from ..schemas import ChartIn, ChartOut
from ..security import current_user

router = APIRouter(prefix="/v1/charts", tags=["charts"])

compute_chart = default_compute_chart


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
        encrypted_birth=encrypted,
        chart_json=json.dumps(chart, ensure_ascii=False),
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        **chart,
        "created_at": record.created_at,
    }


def _owned(db: Session, chart_id: int, user: User) -> Chart:
    record = db.get(Chart, chart_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="星盘不存在")
    return record


@router.get("/{chart_id}", response_model=ChartOut)
def get_chart(
    chart_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    record = _owned(db, chart_id, user)
    data: Dict[str, Any] = json.loads(record.chart_json)
    return {"id": record.id, **data, "created_at": record.created_at}


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
