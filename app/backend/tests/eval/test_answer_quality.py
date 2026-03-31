"""
LLM-as-judge answer quality tests.

These tests use Claude Haiku to evaluate whether answers generated from
retrieved context are faithful (grounded) and relevant (on-topic).

Requirements
────────────
- RUN_EVAL=true environment variable (or the tests are skipped)
- A real ANTHROPIC_API_KEY (not the "test-key-*" placeholder)
- Qdrant running with the eval_documents collection seeded

Quality thresholds (1–5 scale)
─────────────────────────────
  FAITHFULNESS_THRESHOLD = 3.5  — answers must be mostly grounded in context
  RELEVANCY_THRESHOLD    = 3.5  — answers must address the question asked

To run:
  ANTHROPIC_API_KEY=<key> make eval-llm    # from repo root
  RUN_EVAL=true pytest tests/eval/ -v --tb=short -m eval
"""

import os

import pytest

from tests.eval.golden_dataset import GoldenQA
from tests.eval.conftest import LLMJudge, RUN_LLM_EVAL

pytestmark = [pytest.mark.eval, pytest.mark.asyncio(loop_scope="session")]

# ── Quality gate thresholds ────────────────────────────────────────────────────
FAITHFULNESS_THRESHOLD = 3.5
RELEVANCY_THRESHOLD = 3.5


async def _collect_answers(
    eval_rag_tool, golden_qa_with_ids: list[GoldenQA], llm_judge: LLMJudge
) -> list[dict]:
    """Retrieve chunks and generate answers for all golden questions."""
    results = []
    for qa in golden_qa_with_ids:
        await eval_rag_tool.execute(qa.question, top_k=6)
        chunks = eval_rag_tool.last_chunks
        context_texts = [c.content for c in chunks]
        answer = await llm_judge.generate_answer(qa.question, context_texts)
        results.append(
            {
                "question": qa.question,
                "answer": answer,
                "context_texts": context_texts,
                "relevant_keywords": qa.relevant_keywords,
            }
        )
    return results


@pytest.mark.eval
@pytest.mark.skipif(not RUN_LLM_EVAL, reason="Set RUN_EVAL=true to run LLM judge tests")
async def test_answer_faithfulness_meets_threshold(eval_rag_tool, golden_qa_with_ids, llm_judge):
    """Mean faithfulness score across all 12 questions must meet FAITHFULNESS_THRESHOLD."""
    qa_answers = await _collect_answers(eval_rag_tool, golden_qa_with_ids, llm_judge)

    scores = []
    for item in qa_answers:
        result = await llm_judge.score_faithfulness(
            question=item["question"],
            answer=item["answer"],
            context_chunks=item["context_texts"],
        )
        scores.append(result["score"])

    mean_score = sum(scores) / len(scores)
    print(f"\nMean faithfulness = {mean_score:.2f}  (threshold={FAITHFULNESS_THRESHOLD})")
    assert mean_score >= FAITHFULNESS_THRESHOLD, (
        f"Mean faithfulness = {mean_score:.2f} < {FAITHFULNESS_THRESHOLD}. "
        "Answers contain claims not grounded in retrieved context."
    )


@pytest.mark.eval
@pytest.mark.skipif(not RUN_LLM_EVAL, reason="Set RUN_EVAL=true to run LLM judge tests")
async def test_answer_relevancy_meets_threshold(eval_rag_tool, golden_qa_with_ids, llm_judge):
    """Mean relevancy score across all 12 questions must meet RELEVANCY_THRESHOLD."""
    qa_answers = await _collect_answers(eval_rag_tool, golden_qa_with_ids, llm_judge)

    scores = []
    for item in qa_answers:
        result = await llm_judge.score_relevancy(
            question=item["question"],
            answer=item["answer"],
            expected_keywords=item["relevant_keywords"],
        )
        scores.append(result["score"])

    mean_score = sum(scores) / len(scores)
    print(f"\nMean relevancy = {mean_score:.2f}  (threshold={RELEVANCY_THRESHOLD})")
    assert mean_score >= RELEVANCY_THRESHOLD, (
        f"Mean relevancy = {mean_score:.2f} < {RELEVANCY_THRESHOLD}. "
        "Answers are not sufficiently addressing the questions asked."
    )


@pytest.mark.eval
@pytest.mark.skipif(not RUN_LLM_EVAL, reason="Set RUN_EVAL=true to run LLM judge tests")
async def test_per_question_quality_report(eval_rag_tool, golden_qa_with_ids, llm_judge):
    """Diagnostic: print a full per-question quality table. Does not enforce thresholds."""
    qa_answers = await _collect_answers(eval_rag_tool, golden_qa_with_ids, llm_judge)

    print("\n" + "=" * 80)
    print(f"{'#':<3} {'Faith':>6} {'Relev':>6}  Question")
    print("-" * 80)

    faith_scores = []
    relev_scores = []
    for i, (item, qa) in enumerate(zip(qa_answers, golden_qa_with_ids), 1):
        f_result = await llm_judge.score_faithfulness(
            question=item["question"],
            answer=item["answer"],
            context_chunks=item["context_texts"],
        )
        r_result = await llm_judge.score_relevancy(
            question=item["question"],
            answer=item["answer"],
            expected_keywords=item["relevant_keywords"],
        )
        faith_scores.append(f_result["score"])
        relev_scores.append(r_result["score"])
        truncated = qa.question[:58] + "..." if len(qa.question) > 58 else qa.question
        print(f"{i:<3} {f_result['score']:>6.1f} {r_result['score']:>6.1f}  {truncated}")

    print("=" * 80)
    mean_f = sum(faith_scores) / len(faith_scores)
    mean_r = sum(relev_scores) / len(relev_scores)
    print(f"\nOverall — Faithfulness={mean_f:.2f}  Relevancy={mean_r:.2f}")
    # No assertion — diagnostic only
