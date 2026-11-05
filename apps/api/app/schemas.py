from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeviceResponse(BaseModel):
    token: str
    user_id: int


class CommentIn(BaseModel):
    room: str = Field(min_length=1, max_length=120)
    author: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    room: str
    author: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentList(BaseModel):
    items: List[CommentOut]
    next_cursor: Optional[int] = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[int] = None


class ChartIn(BaseModel):
    birth_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    birth_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = Field(min_length=1, max_length=64)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    house_system: str = Field(default="P", pattern=r"^[A-Z]$")


class ChartOut(BaseModel):
    id: int
    planets: List[Dict[str, Any]]
    houses: List[Dict[str, Any]]
    aspects: List[Dict[str, Any]]
    created_at: datetime
