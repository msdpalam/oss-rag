"""
Chat router — agentic RAG pipeline.

POST /chat/stream   → SSE streaming via AgentOrchestrator (tool-use loop + final answer)
POST /chat          → Non-streaming JSON (runs orchestrator, collects full response)

SSE event types emitted:
  {"type": "session",     "session_id": str, "message_id": str}
  {"type": "tool_call",   "tool": str, "input": dict, "step": int}
  {"type": "tool_result", "tool": str, "result": str, "step": int}
  {"type": "delta",       "text": str}
  {"type": "done",        "latency_ms": int, "steps": int, "chunks": [...]}
  {"type": "error",       "message": str}
"""

import json
import time
import uuid
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from agents.episodic_memory import episodic_memory
from agents.orchestrator import AgentOrchestrator
from core.auth import get_current_user
from core.config import settings
from core.database import get_db
from core.models import Document, InvestorProfile, Message, Session, User

router = APIRouter()
log = structlog.get_logger()


# ── Schemas ───────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = None
    rewrite_query: bool = True
    mode: Optional[str] = Field(default=None, pattern="^(strict_rag|expert_context)$")
    agent_id: Optional[str] = None  # e.g. "equity_analyst", "technical_trader", "auto"


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    message_id: str
    steps: int
    chunks: list
    latency_ms: int


# ── Profile helper ────────────────────────────────────────────────────────────


async def _get_investor_profile(user_id, db: AsyncSession) -> dict:
    result = await db.execute(
        select(InvestorProfile).where(InvestorProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        return {}
    return {
        "age": profile.age,
        "risk_tolerance": profile.risk_tolerance,
        "horizon_years": profile.horizon_years,
        "goals": profile.goals or [],
        "portfolio_size_usd": profile.portfolio_size_usd,
        "monthly_contribution_usd": profile.monthly_contribution_usd,
        "tax_accounts": profile.tax_accounts or [],
    }


# ── Session helpers ───────────────────────────────────────────────────────────


async def _get_or_create_session(
    session_id: Optional[str], user_id: uuid.UUID, db: AsyncSession
) -> Session:
    if session_id:
        result = await db.execute(
            select(Session)
            .where(Session.id == uuid.UUID(session_id))
            .where(Session.user_id == user_id)
        )
        sess = result.scalar_one_or_none()
        if sess:
            return sess

    sess = Session(id=uuid.uuid4(), user_id=user_id)
    db.add(sess)
    await db.flush()
    return sess


async def _load_history(session: Session, db: AsyncSession, limit: int = 10) -> List[dict]:
    from sqlalchemy import select

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


async def _persist_exchange(
    db: AsyncSession,
    sess: Session,
    user_message: str,
    answer: str,
    message_id: uuid.UUID,
    chunks: list,
    steps: int,
    latency_ms: int,
) -> None:
    db.add(
        Message(
            id=uuid.uuid4(),
            session_id=sess.id,
            role="user",
            content=user_message,
        )
    )
    db.add(
        Message(
            id=message_id,
            session_id=sess.id,
            role="assistant",
            content=answer,
            retrieved_chunks=chunks,
            latency_ms=latency_ms,
        )
    )
    if not sess.title:
        sess.title = user_message[:80]
    await db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Agentic streaming chat via Server-Sent Events.
    Runs the tool-use loop then streams the final answer.
    """
    # Fetch this user's indexed document IDs for per-user RAG isolation
    doc_result = await db.execute(
        select(Document.id)
        .where(Document.uploaded_by == current_user.id)
        .where(Document.status == "indexed")
    )
    user_doc_ids = [str(r) for r in doc_result.scalars()]
    investor_profile = await _get_investor_profile(current_user.id, db)

    orch = AgentOrchestrator(
        user_document_ids=user_doc_ids,
        agent_id=request.agent_id,
        investor_profile=investor_profile,
        user_id=str(current_user.id),
    )
    sess = await _get_or_create_session(request.session_id, current_user.id, db)
    history = await _load_history(sess, db)
    message_id = uuid.uuid4()

    # Flush the session early so we have its ID before streaming
    await db.commit()

    full_answer: List[str] = []
    final_chunks: list = []
    final_steps: int = 0
    final_latency: int = 0
    final_tickers: List[str] = []
    final_tools: List[str] = []

    async def event_generator():
        nonlocal final_chunks, final_steps, final_latency, final_tickers, final_tools

        async for event in orch.stream(
            user_message=request.message,
            history=history,
            session_id=str(sess.id),
            message_id=str(message_id),
            mode=request.mode,
        ):
            if event["type"] == "delta":
                full_answer.append(event["text"])
            elif event["type"] == "done":
                final_chunks = event.get("chunks", [])
                final_steps = event.get("steps", 0)
                final_latency = event.get("latency_ms", 0)
                final_tickers = event.get("tickers_analyzed", [])
                final_tools = event.get("tools_used", [])

            yield {"data": json.dumps(event)}

        # Persist to DB after streaming completes
        try:
            answer = "".join(full_answer)
            await _persist_exchange(
                db=db,
                sess=sess,
                user_message=request.message,
                answer=answer,
                message_id=message_id,
                chunks=[{k: v for k, v in c.items() if k != "content"} for c in final_chunks],
                steps=final_steps,
                latency_ms=final_latency,
            )
        except Exception as e:
            log.error("chat.persist_failed", error=str(e))

        # Fire-and-forget episodic memory storage (only when tickers were analysed)
        if final_tickers:
            try:
                answer = "".join(full_answer)
                await episodic_memory.store(
                    session_id=str(sess.id),
                    question=request.message,
                    answer=answer,
                    tickers=final_tickers,
                    tools_used=final_tools,
                    domain=settings.AGENT_DOMAIN,
                )
            except Exception as e:
                log.warning("chat.episodic_store_failed", error=str(e))

    return EventSourceResponse(event_generator())


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming chat — collects the full agentic run and returns JSON."""
    t0 = time.monotonic()

    doc_result = await db.execute(
        select(Document.id)
        .where(Document.uploaded_by == current_user.id)
        .where(Document.status == "indexed")
    )
    user_doc_ids = [str(r) for r in doc_result.scalars()]
    investor_profile = await _get_investor_profile(current_user.id, db)

    orch = AgentOrchestrator(
        user_document_ids=user_doc_ids,
        agent_id=request.agent_id,
        investor_profile=investor_profile,
        user_id=str(current_user.id),
    )
    sess = await _get_or_create_session(request.session_id, current_user.id, db)
    history = await _load_history(sess, db)
    message_id = uuid.uuid4()
    await db.commit()

    answer_parts: List[str] = []
    final_chunks: list = []
    final_steps: int = 0
    final_tickers: List[str] = []
    final_tools: List[str] = []

    async for event in orch.stream(
        user_message=request.message,
        history=history,
        session_id=str(sess.id),
        message_id=str(message_id),
        mode=request.mode,
    ):
        if event["type"] == "delta":
            answer_parts.append(event["text"])
        elif event["type"] == "done":
            final_chunks = event.get("chunks", [])
            final_steps = event.get("steps", 0)
            final_tickers = event.get("tickers_analyzed", [])
            final_tools = event.get("tools_used", [])
        elif event["type"] == "error":
            raise HTTPException(status_code=500, detail=event["message"])

    latency_ms = int((time.monotonic() - t0) * 1000)
    answer = "".join(answer_parts)

    await _persist_exchange(
        db=db,
        sess=sess,
        user_message=request.message,
        answer=answer,
        message_id=message_id,
        chunks=final_chunks,
        steps=final_steps,
        latency_ms=latency_ms,
    )

    if final_tickers:
        await episodic_memory.store(
            session_id=str(sess.id),
            question=request.message,
            answer=answer,
            tickers=final_tickers,
            tools_used=final_tools,
            domain=settings.AGENT_DOMAIN,
        )

    return ChatResponse(
        answer=answer,
        session_id=str(sess.id),
        message_id=str(message_id),
        steps=final_steps,
        chunks=final_chunks,
        latency_ms=latency_ms,
    )
