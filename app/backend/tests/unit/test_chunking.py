"""
Unit tests for utils/ingestion.py — chunk splitting logic.

Tests focus on _split_into_chunks() which applies
MIN_CHUNK_CHARS filtering, table handling, and text splitting.
No external services or ML models required.
"""
import pytest

from utils.ingestion import MIN_CHUNK_CHARS, ParsedChunk, _split_into_chunks


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chunk(content: str, content_type: str = "text", page: int = 1) -> ParsedChunk:
    return ParsedChunk(content=content, page_number=page, content_type=content_type)


def long_text(words: int = 200) -> str:
    return ("This is a sentence about financial analysis. " * words)


# ── Minimum size filtering ────────────────────────────────────────────────────

def test_chunk_below_min_chars_is_discarded():
    tiny = make_chunk("Hi")   # well below MIN_CHUNK_CHARS
    assert len(tiny.content) < MIN_CHUNK_CHARS
    result = _split_into_chunks([tiny])
    assert result == []


def test_empty_content_is_discarded():
    assert _split_into_chunks([make_chunk("")]) == []


def test_whitespace_only_is_discarded():
    assert _split_into_chunks([make_chunk("   \n\t  ")]) == []


def test_chunk_at_min_chars_boundary_is_kept():
    content = "x" * MIN_CHUNK_CHARS
    result = _split_into_chunks([make_chunk(content)])
    assert len(result) >= 1


# ── Normal text splitting ─────────────────────────────────────────────────────

def test_long_text_produces_multiple_chunks():
    result = _split_into_chunks([make_chunk(long_text(200))])
    assert len(result) >= 2


def test_all_output_chunks_meet_min_chars():
    result = _split_into_chunks([make_chunk(long_text(100))])
    assert all(len(c.content) >= MIN_CHUNK_CHARS for c in result)


def test_chunk_indices_are_zero_based_and_sequential():
    result = _split_into_chunks([make_chunk(long_text(200))])
    for expected_idx, chunk in enumerate(result):
        assert chunk.chunk_index == expected_idx


def test_page_number_is_preserved_across_sub_chunks():
    chunk = make_chunk(long_text(100), page=7)
    result = _split_into_chunks([chunk])
    assert all(c.page_number == 7 for c in result)


def test_content_type_is_preserved():
    chunk = make_chunk(
        "Image depicts a bar chart showing revenue growth over five years. " * 5,
        content_type="image_caption",
    )
    result = _split_into_chunks([chunk])
    assert all(c.content_type == "image_caption" for c in result)


# ── Table handling ────────────────────────────────────────────────────────────

def test_small_table_kept_whole():
    table = "| Metric | Value |\n|--------|-------|\n| P/E    | 28.5  |\n| P/B    | 6.2   |"
    chunk = make_chunk(table, content_type="table")
    result = _split_into_chunks([chunk])
    assert len(result) == 1
    assert result[0].content == table


def test_small_table_content_type_preserved():
    # Use same table as test_small_table_kept_whole — known to meet MIN_CHUNK_CHARS
    table = "| Metric | Value |\n|--------|-------|\n| P/E    | 28.5  |\n| P/B    | 6.2   |"
    chunk = make_chunk(table, content_type="table")
    result = _split_into_chunks([chunk])
    assert len(result) >= 1
    assert result[0].content_type == "table"


# ── Multiple input chunks ─────────────────────────────────────────────────────

def test_indices_are_global_across_multiple_input_chunks():
    """Chunk indices must be globally sequential, not per-input-chunk."""
    c1 = make_chunk(long_text(100), page=1)
    c2 = make_chunk(long_text(100), page=2)
    result = _split_into_chunks([c1, c2])
    indices = [c.chunk_index for c in result]
    assert indices == list(range(len(result)))


def test_mixed_valid_and_short_chunks():
    valid = make_chunk(long_text(50))
    short = make_chunk("Too short")
    result = _split_into_chunks([valid, short])
    assert all(len(c.content) >= MIN_CHUNK_CHARS for c in result)
