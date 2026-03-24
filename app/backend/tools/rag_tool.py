"""
RAGTool — semantic search over indexed documents.

Retrieval pipeline (all steps are individually feature-flagged):

  1. [Always]      BM25 sparse encode the query
  2. [USE_HYDE]    Generate a hypothetical answer via Claude; use its embedding
                   for the dense search instead of the raw query embedding
  3. [Always]      Dense embed the query (or hypothetical answer)
  4. [USE_HYBRID]  Hybrid search: dense + sparse branches fused via RRF
     [otherwise]   Dense-only search
  5. [USE_RERANKING] CrossEncoder second-pass over RERANK_CANDIDATES → top_k
  6. Format results with source/page metadata for citation
"""
from typing import List, Optional

import structlog

from core.config import settings
from core.embedder import embedder
from core.vector_store import vector_store, RetrievedChunk
from core.sparse_embedder import bm25_encode
from tools.base import BaseTool

log = structlog.get_logger()

_HYDE_PROMPT = (
    "Write a short, factual passage (2-4 sentences) that directly answers the "
    "following question. Use specific numbers, names, and terms as if retrieved "
    "from a financial document. Output only the passage, no preamble.\n\nQuestion: {query}"
)


class RAGTool(BaseTool):
    name = "search_documents"
    description = (
        "Search uploaded documents (annual reports, 10-K filings, earnings transcripts, "
        "research PDFs, news articles) for relevant information. "
        "Use this to find specific figures, quotes, or analysis from uploaded files. "
        "Always call this before answering questions about uploaded documents."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query — use specific financial terms, company names, or metrics",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of excerpts to retrieve (default 6)",
                "default": 6,
            },
        },
        "required": ["query"],
    }

    # Expose retrieved chunks so the orchestrator can surface them as citations
    last_chunks: List[RetrievedChunk] = []

    async def execute(self, query: str, top_k: int = 6) -> str:
        # ── Step 1: Sparse (BM25) encode the query ────────────────────────────
        sparse_indices, sparse_values = bm25_encode(query)
        sparse_vec = (sparse_indices, sparse_values) if sparse_indices else None

        # ── Step 2: Dense encode (optionally via HyDE) ────────────────────────
        dense_query = query
        if settings.USE_HYDE:
            dense_query = await self._generate_hypothesis(query)

        dense_vec = await embedder.embed_one(dense_query)

        # ── Step 3: Retrieve candidates ───────────────────────────────────────
        # When reranking, over-fetch so the cross-encoder has enough to work with
        fetch_k = settings.RERANK_CANDIDATES if settings.USE_RERANKING else top_k

        chunks = await vector_store.search(
            query_vector=dense_vec,
            top_k=fetch_k,
            sparse_vector=sparse_vec,
        )

        # ── Step 4: Re-rank candidates → top_k ───────────────────────────────
        if settings.USE_RERANKING and chunks:
            from core.reranker import reranker
            chunks = await reranker.rerank(query=query, chunks=chunks, top_n=top_k)
        else:
            chunks = chunks[:top_k]

        self.last_chunks = chunks

        if not chunks:
            return "No relevant documents found for this query."

        parts = []
        for c in chunks:
            page_info = f", page {c.page}" if c.page else ""
            parts.append(
                f"[Source: {c.source}{page_info} | score={c.score:.3f}]\n{c.content}"
            )
        return "\n\n---\n\n".join(parts)

    async def _generate_hypothesis(self, query: str) -> str:
        """
        Generate a hypothetical document passage that would answer `query`.
        The hypothesis embedding is typically closer to relevant passages than
        the raw question embedding (HyDE: Hypothetical Document Embeddings).
        Falls back to the original query on any error.
        """
        try:
            from core.claude_client import claude
            response = await claude.create(
                messages=[{"role": "user", "content": _HYDE_PROMPT.format(query=query)}],
                system="You are a financial document expert. Write realistic document passages.",
                max_tokens=settings.HYDE_MAX_TOKENS,
            )
            text = response.content[0].text.strip() if response.content else ""
            log.debug("rag_tool.hyde_generated", query=query[:60], hypothesis=text[:80])
            return text or query
        except Exception as e:
            log.warning("rag_tool.hyde_failed", error=str(e))
            return query
