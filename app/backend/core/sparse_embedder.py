"""
BM25-style sparse encoder — no external dependencies, no corpus required.

Produces (indices, values) pairs for Qdrant SparseVector.

Design rationale
────────────────
Dense embeddings (all-MiniLM-L6-v2) capture semantics but are poor at exact
keyword matching: ticker symbols (AAPL, TSLA), exact dollar figures ($42.5B),
model numbers, and rare proper nouns all embed to near-identical vectors
regardless of content. Sparse BM25 gives each unique token its own dimension,
so "AAPL" at query time matches only chunks that literally contain "AAPL".

Implementation
──────────────
- Tokenise: lowercase, split on non-alphanumeric, keep tokens ≥ 2 chars
- Term frequency (TF): count per token, normalised by document length
- BM25 TF weight: (k1 + 1) * tf / (k1 + tf)  [length-normalisation omitted
  since we have no corpus avgdl; document length normalisation via sqrt]
- Token → index: stable hash (fnv-1a style) modulo VOCAB_SIZE=2^17
  Collision probability per document is negligible at this vocabulary size.

The resulting sparse vectors are self-contained — no shared IDF table needed.
Both document and query vectors use the same function, which is the only
requirement for Qdrant's sparse vector inner-product scoring.
"""
import re
from typing import List, Tuple

# Prime-based hash bucket size — large enough to keep collision rate low
# while fitting Qdrant's SparseVector index efficiently.
VOCAB_SIZE = 131_072   # 2^17

# BM25 k1 parameter (term-frequency saturation)
_K1 = 1.2


def _tokenize(text: str) -> List[str]:
    """Lowercase + split on non-alphanumeric, keep tokens ≥ 2 characters."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) >= 2]


def _fnv1a(s: str) -> int:
    """FNV-1a 32-bit hash — stable across runs, no stdlib hash seed issue."""
    h = 0x811C9DC5
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def bm25_encode(text: str) -> Tuple[List[int], List[float]]:
    """
    Encode *text* into a sparse (indices, values) pair.

    Safe to call on both document chunks (at index time) and queries (at
    search time) — the mapping is deterministic and symmetric.

    Returns empty lists for blank / too-short input; callers should check.
    """
    tokens = _tokenize(text)
    if not tokens:
        return [], []

    # Aggregate TF
    tf_raw: dict[int, int] = {}
    for token in tokens:
        idx = _fnv1a(token) % VOCAB_SIZE
        tf_raw[idx] = tf_raw.get(idx, 0) + 1

    doc_len = len(tokens)

    indices: List[int] = []
    values: List[float] = []
    for idx, freq in tf_raw.items():
        # BM25 TF saturation (no length norm — approximated by sqrt(doc_len))
        tf_norm = freq / (doc_len ** 0.5)
        bm25_tf = (_K1 + 1.0) * tf_norm / (_K1 + tf_norm)
        indices.append(idx)
        values.append(round(bm25_tf, 6))

    return indices, values
