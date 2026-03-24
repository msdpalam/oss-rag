"""
Qdrant vector store wrapper.
Supports dense vector search, sparse (BM25) search, and hybrid (RRF fusion).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from core.config import settings

log = structlog.get_logger()


@dataclass
class RetrievedChunk:
    """A single retrieved chunk with its metadata and score."""

    id: str
    score: float
    content: str
    source: str  # original filename
    page: Optional[int] = None
    chunk_index: Optional[int] = None
    content_type: str = "text"  # text | table | image_caption
    document_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VectorStoreService:
    """
    Async Qdrant client wrapper.
    Collection schema:
      - dense vector:  "dense"   (sentence-transformers, cosine)
      - sparse vector: "sparse"  (BM25/SPLADE for keyword matching)
    """

    DENSE_VECTOR = "dense"
    SPARSE_VECTOR = "sparse"

    def __init__(self) -> None:
        self._client: AsyncQdrantClient | None = None

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=30,
            )
        return self._client

    async def ensure_collection(self) -> None:
        """Create the Qdrant collection if it doesn't exist yet."""
        try:
            await self.client.get_collection(settings.QDRANT_COLLECTION)
            log.info("vector_store.collection_exists", collection=settings.QDRANT_COLLECTION)
        except UnexpectedResponse:
            log.info("vector_store.creating_collection", collection=settings.QDRANT_COLLECTION)
            await self.client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config={
                    self.DENSE_VECTOR: qmodels.VectorParams(
                        size=settings.EMBEDDING_DIMENSIONS,
                        distance=qmodels.Distance.COSINE,
                        on_disk=False,
                    ),
                },
                sparse_vectors_config={
                    self.SPARSE_VECTOR: qmodels.SparseVectorParams(
                        index=qmodels.SparseIndexParams(on_disk=False),
                    ),
                }
                if settings.USE_HYBRID_SEARCH
                else None,
                optimizers_config=qmodels.OptimizersConfigDiff(
                    indexing_threshold=20_000,
                ),
                hnsw_config=qmodels.HnswConfigDiff(m=16, ef_construct=100),
            )
            log.info("vector_store.collection_created")

    async def upsert(self, points: List[Dict[str, Any]]) -> None:
        qdrant_points = []
        for p in points:
            vectors: Dict[str, Any] = {self.DENSE_VECTOR: p["dense_vector"]}
            if settings.USE_HYBRID_SEARCH and "sparse_indices" in p:
                vectors[self.SPARSE_VECTOR] = qmodels.SparseVector(
                    indices=p["sparse_indices"],
                    values=p["sparse_values"],
                )
            qdrant_points.append(
                qmodels.PointStruct(
                    id=str(p["id"]),
                    vector=vectors,
                    payload=p["payload"],
                )
            )

        await self.client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=qdrant_points,
            wait=True,
        )

    async def search(
        self,
        query_vector: List[float],
        top_k: int = None,
        score_threshold: float = None,
        filter_document_ids: Optional[List[str]] = None,
        sparse_vector: Optional[Tuple[List[int], List[float]]] = None,
    ) -> List[RetrievedChunk]:
        """
        Search the documents collection.

        When USE_HYBRID_SEARCH is True and sparse_vector is provided, runs a
        two-branch prefetch (dense + sparse) fused via Reciprocal Rank Fusion.
        Otherwise falls back to dense-only search.

        The RRF score is rank-based (not cosine similarity), so score_threshold
        is only applied in the dense-only path where cosine scores are meaningful.
        """
        top_k = top_k or settings.RETRIEVAL_TOP_K
        score_threshold = score_threshold or settings.RETRIEVAL_SCORE_THRESHOLD

        qdrant_filter = None
        if filter_document_ids:
            qdrant_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchAny(any=filter_document_ids),
                    )
                ]
            )

        if settings.USE_HYBRID_SEARCH and sparse_vector:
            sparse_indices, sparse_values = sparse_vector
            # Over-fetch in each branch so RRF has enough candidates to fuse.
            prefetch_limit = max(top_k * 3, 20)
            response = await self.client.query_points(
                collection_name=settings.QDRANT_COLLECTION,
                prefetch=[
                    qmodels.Prefetch(
                        query=query_vector,
                        using=self.DENSE_VECTOR,
                        limit=prefetch_limit,
                        filter=qdrant_filter,
                    ),
                    qmodels.Prefetch(
                        query=qmodels.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values,
                        ),
                        using=self.SPARSE_VECTOR,
                        limit=prefetch_limit,
                        filter=qdrant_filter,
                    ),
                ],
                query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
                limit=top_k,
                with_payload=True,
                query_filter=qdrant_filter,
            )
            log.debug("vector_store.hybrid_search", top_k=top_k, sparse_terms=len(sparse_indices))
        else:
            response = await self.client.query_points(
                collection_name=settings.QDRANT_COLLECTION,
                query=query_vector,
                using=self.DENSE_VECTOR,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=qdrant_filter,
                with_payload=True,
            )
            log.debug("vector_store.dense_search", top_k=top_k)

        return [self._point_to_chunk(r) for r in response.points]

    async def delete_by_document_id(self, document_id: str) -> None:
        await self.client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )

    async def get_collection_info(self) -> Dict[str, Any]:
        info = await self.client.get_collection(settings.QDRANT_COLLECTION)
        return {
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": str(info.status),
        }

    def _point_to_chunk(self, point: qmodels.ScoredPoint) -> RetrievedChunk:
        p = point.payload or {}
        return RetrievedChunk(
            id=str(point.id),
            score=point.score,
            content=p.get("content", ""),
            source=p.get("source", "unknown"),
            page=p.get("page_number"),
            chunk_index=p.get("chunk_index"),
            content_type=p.get("content_type", "text"),
            document_id=p.get("document_id"),
            metadata={
                k: v
                for k, v in p.items()
                if k
                not in {
                    "content",
                    "source",
                    "page_number",
                    "chunk_index",
                    "content_type",
                    "document_id",
                }
            },
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


# Module-level singleton
vector_store = VectorStoreService()
