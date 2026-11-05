from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from .. import db as dbmod
from ..db import get_db
from ..models import Conversation, Message, User
from ..schemas import ChatIn
from ..security import current_user

router = APIRouter(prefix="/v1/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "你是 Starry Journey 博客的 AI 小助手“大肥鱼”，说话亲切简短、1~3 句，"
    "被问到身份时坦白是 AI。不要编造事实，不聊政治/色情/暴力/违法话题。"
)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_completion(messages: list[dict]):
    """调用 DeepSeek 流式接口，逐段 yield 文本。"""
    if not settings.deepseek_api_key:
        raise RuntimeError("DeepSeek key 未配置")
    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload = {"model": settings.deepseek_model, "messages": messages, "stream": True}
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield delta


@router.post("/stream")
async def chat_stream(
    payload: ChatIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="AI 服务未配置")

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.scalar(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user.id,
            Message.role == "user",
            Message.created_at >= today,
        )
    )
    if used >= settings.daily_message_limit:
        raise HTTPException(status_code=429, detail="今天的对话次数用完啦")

    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        conversation = Conversation(user_id=user.id, title=payload.message[:30])
        db.add(conversation)
        db.flush()

    user_msg = Message(conversation_id=conversation.id, role="user", content=payload.message)
    db.add(user_msg)
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    conv_id, msg_id = conversation.id, user_msg.id

    history = db.scalars(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.id.desc()).limit(12)
    ).all()
    context = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m.role, "content": m.content} for m in reversed(history)
    ]

    async def event_stream():
        parts: list[str] = []
        yield sse("meta", {"conversation_id": conv_id, "message_id": msg_id})
        try:
            async for delta in stream_completion(context):
                parts.append(delta)
                yield sse("delta", {"text": delta})
        except Exception as exc:  # 不把内部细节抛给前端
            print("chat stream error:", repr(exc))
            yield sse("error", {"message": "大肥鱼暂时连不上脑子啦"})
            return

        with dbmod.SessionLocal() as db2:
            db2.add(Message(conversation_id=conv_id, role="assistant", content="".join(parts)))
            conv = db2.get(Conversation, conv_id)
            if conv:
                conv.updated_at = datetime.now(timezone.utc)
            db2.commit()
        yield sse("done", {"chars": len("".join(parts))})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
def list_conversations(
    limit: int = 20,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(min(limit, 50))
    ).all()
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat()} for c in rows]


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .limit(100)
    ).all()
    return [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in rows
    ]
