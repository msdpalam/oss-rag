"""
Pure-Python retrieval quality metrics.

No app imports — these functions operate only on plain Python lists and dicts.
All functions are deterministic and require no external services.

Metrics
-------
- recall_at_k:        fraction of relevant items retrieved in top-K
- reciprocal_rank:    position of first relevant item (1/rank)
- mean_reciprocal_rank: MRR averaged across multiple queries
- dcg_at_k:           Discounted Cumulative Gain (graded relevance)
- ndcg_at_k:          Normalised DCG (0–1 scale)
- compute_retrieval_metrics: convenience wrapper returning all three metrics
"""

import math


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Fraction of relevant items that appear in the top-K retrieved results.

    recall@K = |retrieved[:K] ∩ relevant| / |relevant|

    Returns 0.0 when relevant_ids is empty.
    """
    if not relevant_ids:
        return 0.0
    top_k_set = set(retrieved_ids[:k])
    relevant_set = set(relevant_ids)
    return len(top_k_set & relevant_set) / len(relevant_set)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    """Reciprocal of the rank of the first relevant item in retrieved_ids.

    Returns 1/position (1-indexed) for the first hit, or 0.0 if no relevant
    item appears anywhere in the retrieved list.
    """
    relevant_set = set(relevant_ids)
    for i, rid in enumerate(retrieved_ids):
        if rid in relevant_set:
            return 1.0 / (i + 1)
    return 0.0


def mean_reciprocal_rank(
    per_query_retrieved: list[list[str]],
    per_query_relevant: list[list[str]],
) -> float:
    """Mean Reciprocal Rank across a set of queries.

    Returns 0.0 when the input lists are empty.
    """
    if not per_query_retrieved:
        return 0.0
    rr_scores = [
        reciprocal_rank(retrieved, relevant)
        for retrieved, relevant in zip(per_query_retrieved, per_query_relevant)
    ]
    return sum(rr_scores) / len(rr_scores)


def dcg_at_k(
    retrieved_ids: list[str],
    graded_relevance: dict[str, int],
    k: int,
) -> float:
    """Discounted Cumulative Gain at K.

    dcg@K = Σ rel_i / log2(i + 2)  for i in 0..K-1

    where rel_i = graded_relevance.get(retrieved_ids[i], 0).
    Returns 0.0 when retrieved_ids is empty.
    """
    dcg = 0.0
    for i, rid in enumerate(retrieved_ids[:k]):
        rel = graded_relevance.get(rid, 0)
        dcg += rel / math.log2(i + 2)
    return dcg


def ndcg_at_k(
    retrieved_ids: list[str],
    graded_relevance: dict[str, int],
    k: int,
) -> float:
    """Normalised Discounted Cumulative Gain at K.

    ndcg@K = dcg@K / ideal_dcg@K

    The ideal DCG is computed from the top-K highest relevance grades
    regardless of order. Returns 0.0 when the ideal DCG is 0.
    """
    actual_dcg = dcg_at_k(retrieved_ids, graded_relevance, k)

    # Build ideal ranking: sort all non-zero grades descending, take top K
    sorted_grades = sorted(graded_relevance.values(), reverse=True)[:k]
    ideal_retrieved = [f"ideal_{i}" for i in range(len(sorted_grades))]
    ideal_relevance = {f"ideal_{i}": g for i, g in enumerate(sorted_grades)}
    ideal_dcg = dcg_at_k(ideal_retrieved, ideal_relevance, k)

    if ideal_dcg == 0.0:
        return 0.0
    return actual_dcg / ideal_dcg


def compute_retrieval_metrics(
    per_query_results: list[dict],
    k: int = 6,
) -> dict:
    """Compute Recall@K, MRR, and NDCG@K across a batch of query results.

    Each entry in per_query_results must have:
      - "retrieved_ids":   list[str]  — IDs in ranked order (highest score first)
      - "relevant_ids":    list[str]  — ground-truth relevant IDs
      - "graded_relevance": dict[str, int] — relevance grade per chunk ID

    Returns:
      {
          "recall_at_k": float,
          "mrr":         float,
          "ndcg_at_k":   float,
          "k":           int,
          "n_queries":   int,
      }
    """
    if not per_query_results:
        return {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0, "k": k, "n_queries": 0}

    recall_scores = []
    rr_scores = []
    ndcg_scores = []

    for item in per_query_results:
        retrieved = item["retrieved_ids"]
        relevant = item["relevant_ids"]
        graded = item["graded_relevance"]

        recall_scores.append(recall_at_k(retrieved, relevant, k))
        rr_scores.append(reciprocal_rank(retrieved, relevant))
        ndcg_scores.append(ndcg_at_k(retrieved, graded, k))

    n = len(per_query_results)
    return {
        "recall_at_k": sum(recall_scores) / n,
        "mrr": sum(rr_scores) / n,
        "ndcg_at_k": sum(ndcg_scores) / n,
        "k": k,
        "n_queries": n,
    }
