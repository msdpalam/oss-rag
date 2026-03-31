"""
Integration tests for the messages API.

POST /messages/{id}/feedback  — submit thumbs up/down

Requires: PostgreSQL running (see conftest.py).

Data setup
──────────
The tests insert a real Session + Message row directly via SQLAlchemy so we
can exercise the full feedback round-trip without needing a live Anthropic call.
The rows are cleaned up at the end of the test session via the session-scoped
fixture below.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import os

# ── Session-scoped DB setup ───────────────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb",
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

_TEST_SESSION_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
_TEST_MESSAGE_ID = uuid.UUID("10000000-0000-0000-0000-000000000002")
_ANON_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="session")
async def seeded_message(client):
    """
    Insert a test Session + Message row, yield the message UUID,
    then delete both rows after the test session finishes.

    Uses a raw engine/session (not the app's pool) so we can commit
    independently from the app's transaction lifecycle.
    """
    from core.models import Base, Message, Session

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Ensure the anon user row exists (inserted by init.sql seed or previous run)
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from core.models import User

        await db.execute(
            pg_insert(User)
            .values(id=_ANON_USER_ID, display_name="Anonymous")
            .on_conflict_do_nothing()
        )
        await db.execute(
            pg_insert(Session)
            .values(
                id=_TEST_SESSION_ID,
                user_id=_ANON_USER_ID,
                title="Test session",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                message_count=0,
                is_archived=False,
            )
            .on_conflict_do_nothing()
        )
        await db.execute(
            pg_insert(Message)
            .values(
                id=_TEST_MESSAGE_ID,
                session_id=_TEST_SESSION_ID,
                role="assistant",
                content="Test response for feedback.",
                created_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing()
        )
        await db.commit()

    yield _TEST_MESSAGE_ID

    # Cleanup
    async with async_session() as db:
        await db.execute(delete(Session).where(Session.id == _TEST_SESSION_ID))
        await db.commit()

    await engine.dispose()


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_feedback_invalid_uuid_returns_400(client):
    response = await client.post("/messages/not-a-uuid/feedback", json={"value": "up"})
    assert response.status_code == 400


@pytest.mark.integration
async def test_feedback_nonexistent_message_returns_404(client):
    fake_id = "00000000-0000-0000-0000-000000000097"
    response = await client.post(f"/messages/{fake_id}/feedback", json={"value": "up"})
    assert response.status_code == 404


@pytest.mark.integration
async def test_feedback_invalid_value_returns_422(client):
    """'meh' is not a valid feedback value — Pydantic Literal should reject it."""
    fake_id = "00000000-0000-0000-0000-000000000096"
    response = await client.post(f"/messages/{fake_id}/feedback", json={"value": "meh"})
    assert response.status_code == 422


@pytest.mark.integration
async def test_feedback_thumbs_up_returns_204(client, seeded_message):
    msg_id = str(seeded_message)
    response = await client.post(f"/messages/{msg_id}/feedback", json={"value": "up"})
    assert response.status_code == 204


@pytest.mark.integration
async def test_feedback_persisted_in_messages_list(client, seeded_message):
    """After submitting feedback, GET /sessions/{id}/messages must reflect it."""
    msg_id = str(seeded_message)
    # Submit down vote
    await client.post(f"/messages/{msg_id}/feedback", json={"value": "down"})

    response = await client.get(f"/sessions/{_TEST_SESSION_ID}/messages")
    assert response.status_code == 200
    msgs = response.json()
    target = next((m for m in msgs if m["id"] == msg_id), None)
    assert target is not None
    assert target["feedback"] == "down"
    assert target["feedback_at"] is not None


@pytest.mark.integration
async def test_feedback_can_be_changed(client, seeded_message):
    """Feedback can be overwritten — last write wins."""
    msg_id = str(seeded_message)
    await client.post(f"/messages/{msg_id}/feedback", json={"value": "down"})
    r2 = await client.post(f"/messages/{msg_id}/feedback", json={"value": "up"})
    assert r2.status_code == 204

    response = await client.get(f"/sessions/{_TEST_SESSION_ID}/messages")
    msgs = response.json()
    target = next(m for m in msgs if m["id"] == msg_id)
    assert target["feedback"] == "up"
