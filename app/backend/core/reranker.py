"""
CrossEncoder re-ranker service.

After the vector store returns a broad candidate set (e.g. top-20), the
re-ranker scores every (query, passage) pair jointly and returns the
top-N by cross-encoder score. This second pass catches cases where the
bi-encoder (dense embedding) ranked a highly relevant passage low because
the query and passage use different surface forms.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - ~86 MB, CPU-only, fast (~50–150 ms for 20 passages)
  - Trained on MS-MARCO passage retrieval (question → passage relevance)
  - Outputs unbounded logits; higher = more relevant

Score normalisation
───────────────────
Raw CrossEncoder logits are normalised to [0, 1] via sigmoid so the
downstream citations panel continues to show interpretable scores.
"""

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from typing import List

import structlog

from core.config import settings
from core.vector_store import RetrievedChunk

log = structlog.get_logger()


class RerankerService:
    def __init__(self) -> None:
        self._model = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reranker")

    async def warm_up(self) -> None:
        """Load the CrossEncoder model (called once at startup)."""
        from sentence_transformers import CrossEncoder

        loop = asyncio.get_event_loop()
        try:
            self._model = await loop.run_in_executor(
                self._executor,
                lambda: CrossEncoder(settings.RERANKER_MODEL),
            )
            log.info("reranker.loaded", model=settings.RERANKER_MODEL)
        except Exception as e:
            log.warning("reranker.load_failed", model=settings.RERANKER_MODEL, error=str(e))
            self._model = None  # graceful degradation — rerank() will be a no-op

    async def rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_n: int,
    ) -> List[RetrievedChunk]:
        """
        Score (query, passage) pairs and return the top-N by cross-encoder score.
        Falls back to returning chunks[:top_n] if the model isn't loaded.
        """
        if not self._model or not chunks:
            return chunks[:top_n]

        pairs = [[query, c.content] for c in chunks]
        loop = asyncio.get_event_loop()

        raw_scores: List[float] = await loop.run_in_executor(
            self._executor,
            lambda: self._model.predict(pairs, show_progress_bar=False).tolist(),
        )

        # Sort by raw score, then normalise to [0,1] via sigmoid for display
        ranked = sorted(zip(raw_scores, chunks, strict=False), key=lambda x: x[0], reverse=True)
        result = []
        for raw, chunk in ranked[:top_n]:
            chunk.score = round(1.0 / (1.0 + math.exp(-raw)), 4)
            result.append(chunk)

        log.debug(
            "reranker.done",
            candidates=len(chunks),
            returned=len(result),
            top_score=result[0].score if result else 0,
        )
        return result

    async def close(self) -> None:
        self._executor.shutdown(wait=False)


# Module-level singleton
reranker = RerankerService()
