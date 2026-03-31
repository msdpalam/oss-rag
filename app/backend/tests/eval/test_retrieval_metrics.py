"""
Retrieval quality gate tests.

These tests measure whether the RAG retrieval pipeline finds the right chunks
for each question in the golden dataset. No LLM calls are made — only the
embedder and Qdrant are required.

Quality thresholds
──────────────────
With only 3 chunks in the eval collection and top_k=6 (exceeding the collection
size), every chunk is always returned. The thresholds therefore measure whether
the *correct* chunk is ranked first (MRR), scored highly (NDCG), and present
at all (Recall). Thresholds are deliberately conservative for the initial
baseline; tighten them as the retrieval pipeline matures.

  RECALL_THRESHOLD = 0.6  — at least 60% of relevant chunks in top-6
  MRR_THRESHOLD    = 0.5  — first relevant result in top-2 on average
  NDCG_THRESHOLD   = 0.55 — graded ranking quality above random baseline

To run:
  make eval               # from repo root
  pytest tests/eval/ -v --tb=short -m eval -k "not answer_quality"
"""

import pytest

from tests.eval.golden_dataset import GoldenQA
from tests.eval.metrics.retrieval import compute_retrieval_metrics

pytestmark = [pytest.mark.eval, pytest.mark.asyncio(loop_scope="session")]

# ── Quality gate thresholds ────────────────────────────────────────────────────
RECALL_THRESHOLD = 0.6
MRR_THRESHOLD = 0.5
NDCG_THRESHOLD = 0.55


async def _run_retrieval(eval_rag_tool, golden_qa_with_ids: list[GoldenQA]) -> list[dict]:
    """Run each golden question through the RAGTool and collect results."""
    results = []
    for qa in golden_qa_with_ids:
        await eval_rag_tool.execute(qa.question, top_k=6)
        retrieved_ids = [c.id for c in eval_rag_tool.last_chunks]
        results.append(
            {
                "retrieved_ids": retrieved_ids,
                "relevant_ids": qa.relevant_chunk_ids,
                "graded_relevance": qa.graded_relevance,
                "question": qa.question,
            }
        )
    return results


@pytest.mark.eval
async def test_recall_at_6_meets_threshold(eval_rag_tool, golden_qa_with_ids):
    """Mean Recall@6 across all 12 golden questions must meet RECALL_THRESHOLD."""
    results = await _run_retrieval(eval_rag_tool, golden_qa_with_ids)
    metrics = compute_retrieval_metrics(results, k=6)
    print(f"\nRecall@6 = {metrics['recall_at_k']:.3f}  (threshold={RECALL_THRESHOLD})")
    assert metrics["recall_at_k"] >= RECALL_THRESHOLD, (
        f"Recall@6 = {metrics['recall_at_k']:.3f} < {RECALL_THRESHOLD}. "
        "The retrieval pipeline is not finding relevant chunks often enough."
    )


@pytest.mark.eval
async def test_mrr_meets_threshold(eval_rag_tool, golden_qa_with_ids):
    """Mean Reciprocal Rank across all 12 golden questions must meet MRR_THRESHOLD."""
    results = await _run_retrieval(eval_rag_tool, golden_qa_with_ids)
    metrics = compute_retrieval_metrics(results, k=6)
    print(f"\nMRR = {metrics['mrr']:.3f}  (threshold={MRR_THRESHOLD})")
    assert metrics["mrr"] >= MRR_THRESHOLD, (
        f"MRR = {metrics['mrr']:.3f} < {MRR_THRESHOLD}. "
        "Relevant chunks are not being ranked highly enough."
    )


@pytest.mark.eval
async def test_ndcg_at_6_meets_threshold(eval_rag_tool, golden_qa_with_ids):
    """Mean NDCG@6 across all 12 golden questions must meet NDCG_THRESHOLD."""
    results = await _run_retrieval(eval_rag_tool, golden_qa_with_ids)
    metrics = compute_retrieval_metrics(results, k=6)
    print(f"\nNDCG@6 = {metrics['ndcg_at_k']:.3f}  (threshold={NDCG_THRESHOLD})")
    assert metrics["ndcg_at_k"] >= NDCG_THRESHOLD, (
        f"NDCG@6 = {metrics['ndcg_at_k']:.3f} < {NDCG_THRESHOLD}. "
        "Ranking quality has degraded — relevant chunks are not ranked above noise."
    )


@pytest.mark.eval
async def test_per_query_recall_detail(eval_rag_tool, golden_qa_with_ids):
    """Diagnostic: print per-question recall breakdown. Does not enforce a threshold."""
    results = await _run_retrieval(eval_rag_tool, golden_qa_with_ids)

    from tests.eval.metrics.retrieval import recall_at_k, reciprocal_rank

    print("\n" + "=" * 72)
    print(f"{'#':<3} {'RR':>5} {'R@6':>5}  Question")
    print("-" * 72)
    for i, (item, qa) in enumerate(zip(results, golden_qa_with_ids), 1):
        rr = reciprocal_rank(item["retrieved_ids"], item["relevant_ids"])
        r6 = recall_at_k(item["retrieved_ids"], item["relevant_ids"], k=6)
        truncated = qa.question[:55] + "..." if len(qa.question) > 55 else qa.question
        print(f"{i:<3} {rr:>5.2f} {r6:>5.2f}  {truncated}")
    print("=" * 72)

    overall = compute_retrieval_metrics(results, k=6)
    print(
        f"\nOverall — Recall@6={overall['recall_at_k']:.3f}  "
        f"MRR={overall['mrr']:.3f}  NDCG@6={overall['ndcg_at_k']:.3f}"
    )
    # No assertion — this test always passes; it's for log inspection
