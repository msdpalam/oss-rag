"""
Integration tests for the sessions API.

GET  /sessions           — list sessions
GET  /sessions/{id}      — get single session
GET  /sessions/{id}/messages — list messages

A session is created implicitly when the first chat message is sent.
These tests use the sessions router directly (no LLM call required for list/get).

Requires: PostgreSQL running (see conftest.py).
"""
import pytest


@pytest.mark.integration
async def test_list_sessions_returns_list(client):
    response = await client.get("/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.integration
async def test_list_sessions_response_schema(client):
    """Each session object must contain the expected fields."""
    response = await client.get("/sessions")
    sessions = response.json()
    for sess in sessions:
        assert "id" in sess
        assert "created_at" in sess
        assert "message_count" in sess
        assert "is_archived" in sess


@pytest.mark.integration
async def test_get_nonexistent_session_returns_404(client):
    fake_id = "00000000-0000-0000-0000-000000000099"
    response = await client.get(f"/sessions/{fake_id}")
    assert response.status_code == 404


@pytest.mark.integration
async def test_list_sessions_pagination_params_accepted(client):
    """Pagination query params should not cause an error even if no data exists."""
    response = await client.get("/sessions?limit=5&offset=0")
    assert response.status_code == 200


@pytest.mark.integration
async def test_messages_for_nonexistent_session_returns_404(client):
    fake_id = "00000000-0000-0000-0000-000000000098"
    response = await client.get(f"/sessions/{fake_id}/messages")
    assert response.status_code == 404
