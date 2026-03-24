"""
Unit tests for agents/memory.py — WorkingMemory behaviour.

All tests are pure in-memory — no external services required.
"""
import pytest

from agents.memory import ToolCallRecord, WorkingMemory
from core.vector_store import RetrievedChunk


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chunk(chunk_id: str = "chunk-1", score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        score=score,
        content="Sample content for testing.",
        source="test_doc.pdf",
        page=1,
    )


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_steps_taken_is_zero():
    mem = WorkingMemory(session_id="sess-001")
    assert mem.steps_taken == 0


def test_initial_tool_calls_empty():
    mem = WorkingMemory(session_id="sess-001")
    assert mem.tool_calls == []


def test_initial_rag_chunks_empty():
    mem = WorkingMemory(session_id="sess-001")
    assert mem.rag_chunks == []


# ── record() ─────────────────────────────────────────────────────────────────

def test_record_adds_tool_call():
    mem = WorkingMemory(session_id="sess-001")
    mem.record(step=1, tool_name="get_stock_price", tool_input={"ticker": "AAPL"}, result="$180")
    assert mem.steps_taken == 1
    assert mem.tool_calls[0].tool_name == "get_stock_price"


def test_record_increments_steps_with_each_call():
    mem = WorkingMemory(session_id="sess-001")
    for i in range(5):
        mem.record(step=i + 1, tool_name=f"tool_{i}", tool_input={}, result="ok")
    assert mem.steps_taken == 5


def test_record_stores_input_and_snippet():
    mem = WorkingMemory(session_id="sess-001")
    long_result = "x" * 500
    mem.record(step=1, tool_name="technical_analysis", tool_input={"ticker": "TSLA"}, result=long_result)
    record = mem.tool_calls[0]
    assert record.tool_input == {"ticker": "TSLA"}
    assert len(record.result_snippet) == 300   # capped at 300 chars
    assert len(record.result_full) == 500      # full result preserved


# ── record_rag() ──────────────────────────────────────────────────────────────

def test_record_rag_adds_chunks():
    mem = WorkingMemory(session_id="sess-001")
    mem.record_rag([make_chunk("id-1"), make_chunk("id-2")])
    assert len(mem.rag_chunks) == 2


def test_record_rag_deduplicates_by_id():
    mem = WorkingMemory(session_id="sess-001")
    chunk = make_chunk("id-abc")
    mem.record_rag([chunk])
    mem.record_rag([chunk])           # same chunk added again
    assert len(mem.rag_chunks) == 1


def test_record_rag_accumulates_across_calls():
    mem = WorkingMemory(session_id="sess-001")
    mem.record_rag([make_chunk("id-1"), make_chunk("id-2")])
    mem.record_rag([make_chunk("id-3")])
    assert len(mem.rag_chunks) == 3


def test_record_rag_dedup_across_multiple_calls():
    mem = WorkingMemory(session_id="sess-001")
    mem.record_rag([make_chunk("id-1"), make_chunk("id-2")])
    mem.record_rag([make_chunk("id-2"), make_chunk("id-3")])   # id-2 is a duplicate
    assert len(mem.rag_chunks) == 3


# ── tool_summary() ────────────────────────────────────────────────────────────

def test_tool_summary_empty_returns_sentinel():
    mem = WorkingMemory(session_id="sess-001")
    assert mem.tool_summary() == "No tools called."


def test_tool_summary_contains_tool_name():
    mem = WorkingMemory(session_id="sess-001")
    mem.record(1, "get_stock_price", {"ticker": "AAPL"}, "price=$180")
    assert "get_stock_price" in mem.tool_summary()


def test_tool_summary_contains_input():
    mem = WorkingMemory(session_id="sess-001")
    mem.record(1, "get_fundamentals", {"ticker": "MSFT"}, "P/E=35")
    assert "MSFT" in mem.tool_summary()


def test_tool_summary_lists_all_steps():
    mem = WorkingMemory(session_id="sess-001")
    mem.record(1, "recall_past_analyses", {"query": "AAPL"}, "no prior analyses")
    mem.record(2, "get_stock_price",       {"ticker": "AAPL"}, "price=$185")
    mem.record(3, "technical_analysis",    {"ticker": "AAPL"}, "RSI=42")
    summary = mem.tool_summary()
    assert "recall_past_analyses" in summary
    assert "get_stock_price" in summary
    assert "technical_analysis" in summary
