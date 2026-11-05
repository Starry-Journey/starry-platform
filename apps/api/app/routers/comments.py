from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Comment, User
from ..schemas import CommentIn, CommentList, CommentOut
from ..security import current_user, require_admin

router = APIRouter(prefix="/v1/comments", tags=["comments"])


@router.get("", response_model=CommentList)
def list_comments(
    room: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[int] = None,
    db: Session = Depends(get_db),
):
    stmt = select(Comment).where(Comment.room == room, Comment.status == "visible")
    if cursor:
        stmt = stmt.where(Comment.id < cursor)
    rows = db.scalars(stmt.order_by(Comment.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return CommentList(
        items=[CommentOut.model_validate(r) for r in rows],
        next_cursor=rows[-1].id if has_more and rows else None,
    )


@router.post("", response_model=CommentOut, status_code=201)
def create_comment(
    payload: CommentIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    comment = Comment(
        room=payload.room,
        author=payload.author,
        content=payload.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{comment_id}", status_code=204)
def delete_comment(
    comment_id: int,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    comment = db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    comment.status = "deleted"
    db.commit()
    return None
