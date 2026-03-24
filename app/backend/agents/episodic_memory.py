"""
EpisodicMemoryStore — persists past analyses as searchable vectors in Qdrant.

Each "episode" represents one complete agentic run:
  - what was asked (user question)
  - what tickers were analyzed
  - what the agent concluded (answer summary)
  - when it happened
  - which tools were used

On retrieval, the agent gets semantically relevant past analyses ranked by
similarity to the current query, giving it temporal context:
  "You analyzed AAPL 3 days ago — RSI was 45, now it's 40. Bearish drift."

Storage: separate Qdrant collection ("episodes") — doesn't touch the documents collection.
Embedding: same embedder as documents (all-MiniLM-L6-v2).
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from core.config import settings
from core.embedder import embedder
from core.vector_store import vector_store   # reuses the same AsyncQdrantClient

log = structlog.get_logger()

EPISODES_COLLECTION = "episodes"


class EpisodicMemoryStore:

    async def ensure_collection(self) -> None:
        """Create the episodes Qdrant collection if it doesn't exist."""
        from qdrant_client.http import models as qmodels
        from qdrant_client.http.exceptions import UnexpectedResponse

        try:
            await vector_store.client.get_collection(EPISODES_COLLECTION)
            log.info("episodic_memory.collection_exists")
        except UnexpectedResponse:
            await vector_store.client.create_collection(
                collection_name=EPISODES_COLLECTION,
                vectors_config={
                    "dense": qmodels.VectorParams(
                        size=settings.EMBEDDING_DIMENSIONS,
                        distance=qmodels.Distance.COSINE,
                        on_disk=False,
                    )
                },
                optimizers_config=qmodels.OptimizersConfigDiff(indexing_threshold=1_000),
            )
            log.info("episodic_memory.collection_created")

    async def store(
        self,
        session_id: str,
        question: str,
        answer: str,
        tickers: List[str],
        tools_used: List[str],
        domain: str = "stock_analysis",
    ) -> None:
        """
        Embed and store one episode.
        Called as a fire-and-forget background task — failures are logged, not raised.
        """
        try:
            from qdrant_client.http import models as qmodels

            # Build the text to embed: question + tickers + answer summary
            tickers_str = ", ".join(tickers) if tickers else "unknown"
            embed_text = (
                f"Investment analysis query: {question}\n"
                f"Tickers: {tickers_str}\n"
                f"Analysis summary: {answer[:600]}"
            )

            vector = await embedder.embed_one(embed_text)

            point = qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector={"dense": vector},
                payload={
                    "session_id": session_id,
                    "question": question,
                    "answer_summary": answer[:800],
                    "full_answer": answer,
                    "tickers": tickers,
                    "tools_used": tools_used,
                    "domain": domain,
                    "timestamp": int(datetime.now(tz=timezone.utc).timestamp()),
                    "date_str": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                },
            )

            await vector_store.client.upsert(
                collection_name=EPISODES_COLLECTION,
                points=[point],
                wait=True,
            )
            log.info(
                "episodic_memory.stored",
                session_id=session_id,
                tickers=tickers,
            )

        except Exception as e:
            log.warning("episodic_memory.store_failed", error=str(e))

    async def search(
        self,
        query: str,
        top_k: int = 4,
        ticker_filter: Optional[str] = None,
    ) -> List[dict]:
        """
        Retrieve past episodes semantically similar to the query.
        Optionally filter by ticker.
        Returns a list of episode payloads sorted by score.
        """
        try:
            from qdrant_client.http import models as qmodels

            vector = await embedder.embed_one(query)

            qdrant_filter = None
            if ticker_filter:
                qdrant_filter = qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="tickers",
                            match=qmodels.MatchValue(value=ticker_filter.upper()),
                        )
                    ]
                )

            response = await vector_store.client.query_points(
                collection_name=EPISODES_COLLECTION,
                query=vector,
                using="dense",
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
                score_threshold=0.35,
            )

            return [
                {**p.payload, "relevance_score": round(p.score, 3)}
                for p in response.points
            ]

        except Exception as e:
            log.warning("episodic_memory.search_failed", error=str(e))
            return []

    async def count(self) -> int:
        """Return how many episodes are stored."""
        try:
            info = await vector_store.client.get_collection(EPISODES_COLLECTION)
            return info.points_count or 0
        except Exception:
            return 0


# Module-level singleton
episodic_memory = EpisodicMemoryStore()
