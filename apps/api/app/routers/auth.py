from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiToken, User
from ..schemas import DeviceResponse
from ..security import hash_token, new_token

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/device", response_model=DeviceResponse)
def create_device(db: Session = Depends(get_db)):
    user = User(device_id=uuid.uuid4().hex)
    db.add(user)
    db.flush()

    token = new_token()
    db.add(ApiToken(user_id=user.id, token_hash=hash_token(token)))
    db.commit()
    return DeviceResponse(token=token, user_id=user.id)
