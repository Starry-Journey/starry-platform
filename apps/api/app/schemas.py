from __future__ import annotations

from datetime import datetime
from typing import List, Optional

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
