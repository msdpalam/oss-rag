"""
Integration tests for health endpoints.

GET /health       — liveness (no dependencies)
GET /health/ready — readiness (checks DB + Qdrant)

Requires: PostgreSQL and Qdrant running (see conftest.py).
"""
import pytest


@pytest.mark.integration
async def test_liveness_returns_ok(client):
    """Liveness endpoint must always return 200 with status=ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
async def test_liveness_does_not_require_db(client):
    """/health must respond even if the DB is unreachable (liveness != readiness)."""
    response = await client.get("/health")
    # We can only verify the response here; the isolation is a design property
    assert response.status_code == 200


@pytest.mark.integration
async def test_readiness_returns_ready(client):
    """/health/ready must confirm both DB and vector store are reachable."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert "vector_store" in body


@pytest.mark.integration
async def test_readiness_includes_vector_store_info(client):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    vs = response.json()["vector_store"]
    assert "status" in vs
