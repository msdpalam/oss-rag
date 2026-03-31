"""
Eval test fixtures.

Strategy
────────
- Real Qdrant (provided by CI docker service or local stack)
- Real embedder model (sentence-transformers/all-MiniLM-L6-v2) — intentionally
  NOT mocked; eval measures actual retrieval quality
- Dedicated 'eval_documents' Qdrant collection — created fresh each session
  and torn down afterwards; never touches the app's 'documents' collection
- No FastAPI app, no PostgreSQL — eval bypasses the application entirely
- RAGTool is wired to the eval collection via direct patching of the
  vector_store singleton and settings overrides
- LLM judge (Claude Haiku) is only instantiated when RUN_EVAL=true

Environment variables
─────────────────────
  QDRANT_URL        — defaults to http://localhost:6333
  ANTHROPIC_API_KEY — required only when RUN_EVAL=true
  RUN_EVAL          — set to "true"/"1" to enable LLM-as-judge tests
"""

import copy
import json
import os
from unittest.mock import patch

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-eval-not-real")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "ragapp")
os.environ.setdefault("S3_SECRET_KEY", "ragapp123")

# Must be set before importing app modules so pydantic-settings picks them up
from core.config import settings  # noqa: E402
from core.embedder import embedder  # noqa: E402
from core.sparse_embedder import bm25_encode  # noqa: E402
from core.vector_store import vector_store  # noqa: E402
from tests.eval.golden_dataset import (  # noqa: E402
    EVAL_CHUNK_IDS,
    GOLDEN_QA_DATASET,
    SYNTHETIC_PARAGRAPHS,
    GoldenQA,
)
# RAGTool is imported inside the fixture to avoid the circular import chain:
# tools/__init__.py → recall_tool → agents/episodic_memory → agents/orchestrator → tools

EVAL_COLLECTION = "eval_documents"
RUN_LLM_EVAL = os.environ.get("RUN_EVAL", "").lower() in ("1", "true", "yes")

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"


# ── Real embedder ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
async def real_embedder():
    """Load the actual sentence-transformers model (all-MiniLM-L6-v2, ~90MB).
    This is intentionally NOT mocked — eval needs real semantic embeddings."""
    await embedder.warm_up()
    return embedder


# ── Dedicated eval Qdrant client ──────────────────────────────────────────────

@pytest.fixture(scope="session")
async def eval_qdrant_client():
    """Bare AsyncQdrantClient pointed at QDRANT_URL, independent of the app singleton."""
    client = AsyncQdrantClient(url=os.environ["QDRANT_URL"], timeout=30)
    yield client
    await client.close()


# ── Eval collection lifecycle ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
async def eval_collection(eval_qdrant_client: AsyncQdrantClient):
    """Create a fresh 'eval_documents' collection; delete it on teardown.

    Always creates both dense and sparse vectors regardless of USE_HYBRID_SEARCH
    so that the eval is consistent across flag configurations.
    """
    # Drop if leftover from a previous failed session
    try:
        await eval_qdrant_client.delete_collection(EVAL_COLLECTION)
    except Exception:
        pass

    await eval_qdrant_client.create_collection(
        collection_name=EVAL_COLLECTION,
        vectors_config={
            DENSE_VECTOR: qmodels.VectorParams(
                size=settings.EMBEDDING_DIMENSIONS,
                distance=qmodels.Distance.COSINE,
                on_disk=False,
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR: qmodels.SparseVectorParams(
                index=qmodels.SparseIndexParams(on_disk=False),
            ),
        },
    )

    yield EVAL_COLLECTION

    # Teardown — delete the collection so it doesn't persist between runs
    try:
        await eval_qdrant_client.delete_collection(EVAL_COLLECTION)
    except Exception:
        pass


# ── Seed synthetic chunks ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
async def seeded_eval_chunks(
    eval_collection: str,
    eval_qdrant_client: AsyncQdrantClient,
    real_embedder,
):
    """Embed the 3 synthetic paragraphs and upsert them into the eval collection.

    Uses EVAL_CHUNK_IDS for deterministic point IDs so that graded_relevance
    in the golden dataset can reference stable IDs.

    Returns: list of {id, content, paragraph_index}
    """
    dense_vectors = await real_embedder.embed(SYNTHETIC_PARAGRAPHS)

    points = []
    for i, (content, dense_vec, chunk_id) in enumerate(
        zip(SYNTHETIC_PARAGRAPHS, dense_vectors, EVAL_CHUNK_IDS)
    ):
        sparse_indices, sparse_values = bm25_encode(content)
        vectors: dict = {DENSE_VECTOR: dense_vec}
        if sparse_indices:
            vectors[SPARSE_VECTOR] = qmodels.SparseVector(
                indices=sparse_indices,
                values=sparse_values,
            )
        points.append(
            qmodels.PointStruct(
                id=chunk_id,
                vector=vectors,
                payload={
                    "content": content,
                    "source": "acme_eval_doc.txt",
                    "page_number": None,
                    "chunk_index": i,
                    "content_type": "text",
                    "document_id": "eval-doc-00000000-0000-0000-0000-000000000000",
                },
            )
        )

    await eval_qdrant_client.upsert(
        collection_name=eval_collection,
        points=points,
        wait=True,
    )

    return [
        {"id": chunk_id, "content": para, "paragraph_index": i}
        for i, (chunk_id, para) in enumerate(zip(EVAL_CHUNK_IDS, SYNTHETIC_PARAGRAPHS))
    ]


# ── Golden QA with resolved chunk IDs ─────────────────────────────────────────

@pytest.fixture(scope="session")
def golden_qa_with_ids(seeded_eval_chunks):
    """Return the golden Q&A dataset with relevant_chunk_ids populated.

    Resolves each GoldenQA.source_paragraph_index → EVAL_CHUNK_IDS[index],
    and converts graded_relevance keys from paragraph indices to chunk IDs.
    """
    resolved = []
    for qa in GOLDEN_QA_DATASET:
        qa_copy = copy.deepcopy(qa)
        # primary relevant chunk
        qa_copy.relevant_chunk_ids = [EVAL_CHUNK_IDS[qa_copy.source_paragraph_index]]
        # also include any grade-1 chunks as relevant for recall purposes
        for para_idx, grade in qa_copy.graded_relevance.items():
            if grade > 0:
                cid = EVAL_CHUNK_IDS[para_idx]
                if cid not in qa_copy.relevant_chunk_ids:
                    qa_copy.relevant_chunk_ids.append(cid)
        # convert graded_relevance keys from int paragraph index to chunk ID string
        qa_copy.graded_relevance = {
            EVAL_CHUNK_IDS[para_idx]: grade
            for para_idx, grade in qa_copy.graded_relevance.items()
        }
        resolved.append(qa_copy)
    return resolved


# ── RAGTool wired to eval collection ─────────────────────────────────────────

@pytest.fixture(scope="session")
def eval_rag_tool(eval_collection, eval_qdrant_client, real_embedder):
    """RAGTool instance redirected to the eval collection.

    Patches applied for the duration of the session:
    - vector_store._client → eval_qdrant_client (bypasses lazy-init)
    - settings.QDRANT_COLLECTION → "eval_documents"
    - settings.USE_RERANKING → False  (avoids CrossEncoder model download)
    - settings.USE_HYDE → False       (avoids spurious Claude calls)
    """
    # Deferred import avoids circular: tools/__init__ → recall_tool → agents → tools
    from tools.rag_tool import RAGTool  # noqa: PLC0415

    tool = RAGTool()

    # Direct attribute set to bypass the lazy-init property
    original_client = vector_store._client
    vector_store._client = eval_qdrant_client

    with (
        patch.object(settings, "QDRANT_COLLECTION", EVAL_COLLECTION),
        patch.object(settings, "USE_RERANKING", False),
        patch.object(settings, "USE_HYDE", False),
    ):
        yield tool

    # Restore original client (may be None if never initialised)
    vector_store._client = original_client


# ── LLM judge ─────────────────────────────────────────────────────────────────

class LLMJudge:
    """LLM-as-judge for answer faithfulness and relevancy.

    Uses claude-haiku (cheapest model) via AsyncAnthropic directly.
    Returns structured scores on a 1-5 scale.
    """

    _FAITHFULNESS_PROMPT = (
        "You are an evaluation judge for a RAG (retrieval-augmented generation) system.\n\n"
        "Assess whether the ANSWER contains ONLY claims supported by the CONTEXT passages.\n\n"
        "CONTEXT:\n{context}\n\n"
        "QUESTION: {question}\n"
        "ANSWER: {answer}\n\n"
        "Rate faithfulness 1-5:\n"
        "5 = Every claim directly supported by context\n"
        "4 = Almost all claims supported; minor paraphrasing\n"
        "3 = Most claims supported but 1-2 go beyond context\n"
        "2 = Several claims not grounded in context\n"
        "1 = Significant hallucination or contradicts context\n\n"
        'Respond with JSON only: {{"score": <1-5>, "reasoning": "<one sentence>"}}'
    )

    _RELEVANCY_PROMPT = (
        "You are an evaluation judge for a question-answering system.\n\n"
        "Assess whether the ANSWER addresses the QUESTION asked.\n\n"
        "QUESTION: {question}\n"
        "ANSWER: {answer}\n"
        "EXPECTED CONCEPTS: {expected_keywords}\n\n"
        "Rate answer relevancy 1-5:\n"
        "5 = Directly and completely addresses the question, includes key concepts\n"
        "4 = Addresses the question but may omit one minor concept\n"
        "3 = Partially relevant but misses important aspects\n"
        "2 = Tangentially related but doesn't really answer\n"
        "1 = Does not address the question\n\n"
        'Respond with JSON only: {{"score": <1-5>, "reasoning": "<one sentence>"}}'
    )

    def __init__(self, api_key: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)

    async def _judge(self, prompt: str) -> dict:
        response = await self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        try:
            return json.loads(text)
        except Exception:
            # Fallback if Claude wraps JSON in markdown
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"score": 3, "reasoning": "parse error"}

    async def score_faithfulness(
        self, question: str, answer: str, context_chunks: list[str]
    ) -> dict:
        context = "\n---\n".join(context_chunks)
        prompt = self._FAITHFULNESS_PROMPT.format(
            context=context, question=question, answer=answer
        )
        return await self._judge(prompt)

    async def score_relevancy(
        self, question: str, answer: str, expected_keywords: list[str]
    ) -> dict:
        prompt = self._RELEVANCY_PROMPT.format(
            question=question,
            answer=answer,
            expected_keywords=", ".join(expected_keywords),
        )
        return await self._judge(prompt)

    async def generate_answer(self, question: str, context_chunks: list[str]) -> str:
        """Generate an answer for a question given retrieved context chunks."""
        context = "\n---\n".join(context_chunks)
        response = await self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Answer the following question using ONLY the provided context. "
                        f"Be concise.\n\n"
                        f"CONTEXT:\n{context}\n\n"
                        f"QUESTION: {question}"
                    ),
                }
            ],
        )
        return response.content[0].text.strip()


@pytest.fixture(scope="session")
def llm_judge():
    """LLMJudge instance — skipped unless RUN_EVAL=true."""
    if not RUN_LLM_EVAL:
        pytest.skip("LLM judge disabled — set RUN_EVAL=true to enable")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("test-key"):
        pytest.skip("Real ANTHROPIC_API_KEY required for LLM judge tests")
    return LLMJudge(api_key=api_key)
