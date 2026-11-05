from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ApiToken, User


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return "st_" + secrets.token_urlsafe(32)


def current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少令牌")
    token = authorization[len("Bearer ") :].strip()
    record = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(token)))
    if not record:
        raise HTTPException(status_code=401, detail="令牌无效")
    return record.user


def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    from .config import settings

    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="需要管理员权限")
