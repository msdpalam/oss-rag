"""
Integration test fixtures.

Strategy
────────
- Real PostgreSQL and Qdrant (provided by CI docker services or local stack)
- ML models (embedder, reranker) are patched to no-ops — they're covered by
  unit tests and we don't want 90s model downloads in every CI run
- Anthropic API is patched — no real API calls, no key needed in CI
- MinIO is not required for these tests (health + session endpoints don't use it)
- asgi_lifespan.LifespanManager explicitly triggers FastAPI startup/shutdown so
  that init_db() and ensure_collection() run before any test makes a request
- Tests are marked with loop_scope="session" (in test files via pytestmark) so
  they share the same event loop as the session-scoped client fixture; this
  prevents asyncpg / qdrant-client connections from being "attached to a
  different loop"

Environment variables
─────────────────────
Set these in CI (or your shell) before running:
  DATABASE_URL  — defaults to localhost:5432 postgres
  QDRANT_URL    — defaults to localhost:6333
  ANTHROPIC_API_KEY — set to any non-empty string (patched, never called)
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

# ── Required env vars before any app import ───────────────────────────────────
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-ci-not-real")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb",
)
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "ragapp")
os.environ.setdefault("S3_SECRET_KEY", "ragapp123")


@pytest.fixture(scope="session")
def patch_ml_startup():
    """
    Prevent model downloads during test collection/startup.
    The embedder and reranker are covered by unit tests; here we just need
    the HTTP API to start cleanly.
    """
    with (
        patch("core.embedder.EmbedderService.warm_up", new_callable=AsyncMock),
        patch("core.reranker.RerankerService.warm_up", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture(scope="session")
async def client(patch_ml_startup):
    """
    Async HTTP client pointed at the full FastAPI app.
    LifespanManager explicitly sends ASGI lifespan startup/shutdown events
    so that init_db() and ensure_collection() run before any request.
    Session-scoped so all tests share one asyncpg pool and qdrant client.
    """
    from main import app

    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac:
            yield ac
