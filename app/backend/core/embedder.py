"""
Sentence-transformers async wrapper.
Runs the CPU-bound encode() call in a thread pool to avoid blocking the event loop.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List

import structlog

from core.config import settings

log = structlog.get_logger()


class EmbedderService:
    def __init__(self) -> None:
        self._model = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedder")

    @property
    def model(self):
        if self._model is None:
            raise RuntimeError("Embedder not warmed up — call warm_up() first.")
        return self._model

    async def warm_up(self) -> None:
        """Load the model into memory (called once at startup)."""
        from sentence_transformers import SentenceTransformer

        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            self._executor,
            lambda: SentenceTransformer(settings.EMBEDDING_MODEL, device=settings.EMBEDDING_DEVICE),
        )
        log.info(
            "embedder.loaded",
            model=settings.EMBEDDING_MODEL,
            device=settings.EMBEDDING_DEVICE,
        )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts. Returns a list of float vectors."""
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(
            self._executor,
            lambda: self.model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
            ).tolist(),
        )
        return vectors

    async def embed_one(self, text: str) -> List[float]:
        vectors = await self.embed([text])
        return vectors[0]

    async def close(self) -> None:
        self._executor.shutdown(wait=False)


embedder = EmbedderService()
