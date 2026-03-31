"""
Messages router — feedback on individual messages.

POST /messages/{id}/feedback  — submit thumbs up/down on an assistant message
"""

import uuid
from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.database import get_db
from core.models import Message, Session, User

router = APIRouter()
log = structlog.get_logger()


class FeedbackRequest(BaseModel):
    value: Literal["up", "down"]


@router.post("/{message_id}/feedback", status_code=204)
async def submit_feedback(
    message_id: str,
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        mid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID")

    result = await db.execute(select(Message).where(Message.id == mid))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Verify the message belongs to a session owned by this user
    sess_result = await db.execute(
        select(Session)
        .where(Session.id == msg.session_id)
        .where(Session.user_id == current_user.id)
    )
    if not sess_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Message not found")

    msg.feedback = body.value
    msg.feedback_at = datetime.utcnow()
    await db.commit()
    log.info("feedback.submitted", message_id=str(mid), value=body.value)
