"""
Sessions router — CRUD for chat sessions and message history.

GET  /sessions                    — list sessions for anonymous user
DELETE /sessions/{id}             — delete session and all its messages
GET  /sessions/{id}/messages      — get all messages in a session
"""
import uuid
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.models import Message, Session

router = APIRouter()
log = structlog.get_logger()

ANON_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ── Response schemas ──────────────────────────────────────────────────────────

class SessionResponse(BaseModel):
    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    last_message_at: Optional[str]
    message_count: int
    is_archived: bool

    @classmethod
    def from_orm(cls, s: Session) -> "SessionResponse":
        return cls(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
            last_message_at=s.last_message_at.isoformat() if s.last_message_at else None,
            message_count=s.message_count,
            is_archived=s.is_archived,
        )


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    retrieved_chunks: Optional[list]
    search_query: Optional[str]
    model_used: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    latency_ms: Optional[int]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[SessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .where(Session.user_id == ANON_USER_ID)
        .where(Session.is_archived == False)
        .order_by(Session.updated_at.desc())
        .limit(50)
    )
    return [SessionResponse.from_orm(s) for s in result.scalars()]


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.execute(select(Session).where(Session.id == sid))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(sess)
    await db.commit()


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == sid)
        .order_by(Message.created_at.asc())
    )
    return [
        MessageResponse(
            id=str(m.id),
            session_id=str(m.session_id),
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat(),
            retrieved_chunks=m.retrieved_chunks,
            search_query=m.search_query,
            model_used=m.model_used,
            prompt_tokens=m.prompt_tokens,
            completion_tokens=m.completion_tokens,
            latency_ms=m.latency_ms,
        )
        for m in result.scalars()
    ]
