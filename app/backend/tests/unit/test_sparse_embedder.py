"""
Unit tests for core/sparse_embedder.py — BM25 tokenisation and encoding.

These tests require no external services.
All assertions are on pure-function behaviour.
"""
import pytest

from core.sparse_embedder import VOCAB_SIZE, _fnv1a, _tokenize, bm25_encode


# ── _tokenize ─────────────────────────────────────────────────────────────────

def test_tokenize_lowercases():
    assert _tokenize("AAPL Revenue") == ["aapl", "revenue"]


def test_tokenize_splits_on_non_alphanumeric():
    tokens = _tokenize("Apple,Inc.$42.5B")
    assert "apple" in tokens
    assert "inc" in tokens
    assert "42" in tokens


def test_tokenize_filters_single_char_tokens():
    tokens = _tokenize("a b c the AAPL")
    assert "a" not in tokens
    assert "b" not in tokens
    assert "c" not in tokens
    assert "aapl" in tokens


def test_tokenize_handles_numbers():
    tokens = _tokenize("Q3 2023 revenue $81.8B")
    assert "q3" in tokens
    assert "2023" in tokens
    assert "revenue" in tokens


def test_tokenize_empty_string():
    assert _tokenize("") == []


def test_tokenize_only_punctuation():
    assert _tokenize("---!!!...") == []


# ── _fnv1a ────────────────────────────────────────────────────────────────────

def test_fnv1a_deterministic():
    assert _fnv1a("aapl") == _fnv1a("aapl")


def test_fnv1a_different_tokens_differ():
    assert _fnv1a("aapl") != _fnv1a("tsla")


def test_fnv1a_returns_non_negative():
    assert _fnv1a("any token") >= 0


# ── bm25_encode ───────────────────────────────────────────────────────────────

def test_bm25_encode_empty_string():
    indices, values = bm25_encode("")
    assert indices == [] and values == []


def test_bm25_encode_returns_equal_length_lists():
    indices, values = bm25_encode("AAPL fundamental analysis DCF valuation")
    assert len(indices) == len(values)


def test_bm25_encode_unique_indices():
    # Repeated tokens should collapse to one entry per unique token
    indices, _ = bm25_encode("revenue revenue revenue growth growth")
    assert len(indices) == len(set(indices))


def test_bm25_encode_non_negative_values():
    _, values = bm25_encode("AAPL TSLA MSFT valuation revenue margins")
    assert all(v > 0 for v in values)


def test_bm25_encode_deterministic():
    text = "Apple Inc. AAPL quarterly earnings revenue growth margin"
    assert bm25_encode(text) == bm25_encode(text)


def test_bm25_encode_indices_within_vocab():
    indices, _ = bm25_encode("the quick brown fox jumps over the lazy dog")
    assert all(0 <= i < VOCAB_SIZE for i in indices)


def test_bm25_encode_single_token():
    indices, values = bm25_encode("AAPL")
    assert len(indices) == 1
    assert len(values) == 1
    assert values[0] > 0


def test_bm25_encode_higher_tf_raises_value():
    """A token that appears more often should have a higher (but saturating) BM25 score."""
    _, vals_single = bm25_encode("aapl")
    _, vals_repeated = bm25_encode("aapl aapl aapl aapl aapl")
    # BM25 saturation: repeated token value should be higher but not linearly
    assert vals_repeated[0] > vals_single[0]


def test_bm25_encode_query_and_doc_same_function():
    """Query and document encoding must use the same token→index mapping."""
    q_indices, _ = bm25_encode("AAPL revenue")
    d_indices, _ = bm25_encode("AAPL revenue growth margins")
    # All query tokens should also appear in the document (it's a superset)
    q_set = set(q_indices)
    d_set = set(d_indices)
    assert q_set.issubset(d_set)
