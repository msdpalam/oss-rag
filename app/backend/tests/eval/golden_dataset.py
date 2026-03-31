"""
Golden Q&A dataset for retrieval and answer quality evaluation.

The evaluation is fully self-contained — it does NOT depend on any documents
uploaded by the user. Instead, a synthetic 3-paragraph document about the
fictional company "Acme Corp" (ticker: ACME) is seeded into a dedicated Qdrant
collection (`eval_documents`) at the start of each eval session and torn down
afterwards.

Each paragraph covers a distinct stock analysis topic so that retrieval
boundaries are clean and measurable:
  - Paragraph 0: DCF valuation & revenue growth
  - Paragraph 1: Q3 2024 earnings & margin drivers
  - Paragraph 2: Risk factors (concentration, regulatory, interest rates)

The 12 golden Q&A pairs are distributed 4-per-paragraph. Graded relevance is
encoded per paragraph index (not chunk ID); the eval conftest resolves these to
real Qdrant point IDs after seeding.
"""

from dataclasses import dataclass, field


# ── Deterministic Qdrant point IDs ────────────────────────────────────────────
# These are fixed so that graded_relevance can reference stable IDs across runs.
EVAL_CHUNK_IDS: list[str] = [
    "e0000000-0000-0000-0000-000000000001",  # paragraph 0 — DCF / valuation
    "e0000000-0000-0000-0000-000000000002",  # paragraph 1 — earnings / margins
    "e0000000-0000-0000-0000-000000000003",  # paragraph 2 — risk factors
]

# ── Synthetic document content ────────────────────────────────────────────────
SYNTHETIC_PARAGRAPHS: list[str] = [
    # Paragraph 0 — DCF valuation & revenue growth
    (
        "Acme Corp (ticker: ACME) reported fiscal year 2024 revenue of $4.2 billion, "
        "a 17% increase year-over-year. The company's discounted cash flow (DCF) "
        "valuation, using a weighted average cost of capital (WACC) of 10% and a "
        "terminal growth rate of 3%, yields an intrinsic value of $87 per share. "
        "The current price-to-earnings (P/E) ratio stands at 24x, which is below "
        "the sector median of 28x, suggesting the stock may be undervalued relative "
        "to peers."
    ),
    # Paragraph 1 — Q3 2024 earnings & margin drivers
    (
        "In the third quarter of fiscal year 2024, Acme Corp achieved gross margins "
        "of 62%, up from 58% in Q3 2023, driven primarily by software subscription "
        "revenue growth of 34%. Operating expenses totalled $820 million, with "
        "research and development (R&D) representing 22% of total revenue. Net income "
        "came in at $310 million, beating analyst consensus estimates of $285 million "
        "by 8.8%, marking the fourth consecutive quarter of earnings beats."
    ),
    # Paragraph 2 — Risk factors
    (
        "Key risk factors for Acme Corp include customer concentration risk — the "
        "top three customers account for 41% of annual recurring revenue (ARR). "
        "The company also faces regulatory headwinds in the European Union under the "
        "Digital Markets Act, which could compress operating margins by an estimated "
        "3 to 5 percentage points. Additionally, rising interest rates increase the "
        "WACC discount rate used in DCF models, reducing the intrinsic value estimate "
        "by approximately $6 per share for each 100 basis points increase in rates."
    ),
]

SYNTHETIC_DOCUMENT = "\n\n".join(SYNTHETIC_PARAGRAPHS)


# ── GoldenQA dataclass ────────────────────────────────────────────────────────
@dataclass
class GoldenQA:
    question: str
    answer_summary: str  # what a correct answer should convey
    source_paragraph_index: int  # 0/1/2 — primary source paragraph
    relevant_keywords: list[str]  # key terms the answer should include
    # graded_relevance keyed by paragraph_index (0/1/2); resolved to chunk IDs
    # by the eval conftest after Qdrant seeding.
    graded_relevance: dict[int, int] = field(default_factory=dict)
    # Populated by conftest.golden_qa_with_ids fixture
    relevant_chunk_ids: list[str] = field(default_factory=list)


# ── 12 golden Q&A pairs ───────────────────────────────────────────────────────
# Graded relevance:  2 = primary source,  1 = adjacent/related,  0 = unrelated
GOLDEN_QA_DATASET: list[GoldenQA] = [
    # ── Paragraph 0: DCF / valuation ─────────────────────────────────────────
    GoldenQA(
        question="What is Acme Corp's intrinsic value per share according to DCF analysis?",
        answer_summary="The DCF intrinsic value is $87 per share.",
        source_paragraph_index=0,
        relevant_keywords=["$87", "intrinsic value", "DCF"],
        graded_relevance={0: 2, 1: 0, 2: 1},  # P2 mentions DCF/WACC in risk context
    ),
    GoldenQA(
        question="What WACC and terminal growth rate were used in the Acme Corp valuation?",
        answer_summary="WACC of 10% and terminal growth rate of 3% were used.",
        source_paragraph_index=0,
        relevant_keywords=["10%", "WACC", "3%", "terminal growth rate"],
        graded_relevance={0: 2, 1: 0, 2: 1},
    ),
    GoldenQA(
        question="How does Acme Corp's P/E ratio compare to its sector peers?",
        answer_summary="Acme Corp's P/E of 24x is below the sector median of 28x, suggesting undervaluation.",
        source_paragraph_index=0,
        relevant_keywords=["24x", "28x", "sector median", "undervalued"],
        graded_relevance={0: 2, 1: 0, 2: 0},
    ),
    GoldenQA(
        question="What was Acme Corp's revenue and revenue growth rate in fiscal year 2024?",
        answer_summary="Revenue was $4.2 billion, up 17% year-over-year.",
        source_paragraph_index=0,
        relevant_keywords=["$4.2 billion", "17%", "revenue", "year-over-year"],
        graded_relevance={0: 2, 1: 0, 2: 0},
    ),
    # ── Paragraph 1: Q3 2024 earnings & margins ───────────────────────────────
    GoldenQA(
        question="What were Acme Corp's gross margins in Q3 2024 and how did they change?",
        answer_summary="Gross margins were 62% in Q3 2024, up from 58% in Q3 2023.",
        source_paragraph_index=1,
        relevant_keywords=["62%", "gross margin", "Q3 2024", "58%"],
        graded_relevance={0: 0, 1: 2, 2: 0},
    ),
    GoldenQA(
        question="By how much did Acme Corp beat analyst earnings estimates in Q3 2024?",
        answer_summary="Net income of $310M beat consensus of $285M by 8.8%.",
        source_paragraph_index=1,
        relevant_keywords=["$310 million", "$285 million", "8.8%", "consensus"],
        graded_relevance={0: 0, 1: 2, 2: 0},
    ),
    GoldenQA(
        question="What drove Acme Corp's margin improvement in Q3 2024?",
        answer_summary="Software subscription revenue growth of 34% drove the margin improvement.",
        source_paragraph_index=1,
        relevant_keywords=["software subscription", "34%", "margin"],
        graded_relevance={0: 0, 1: 2, 2: 0},
    ),
    GoldenQA(
        question="What percentage of Acme Corp's revenue is spent on R&D?",
        answer_summary="R&D represents 22% of total revenue.",
        source_paragraph_index=1,
        relevant_keywords=["22%", "R&D", "research and development", "revenue"],
        graded_relevance={0: 0, 1: 2, 2: 0},
    ),
    # ── Paragraph 2: Risk factors ─────────────────────────────────────────────
    GoldenQA(
        question="What customer concentration risk does Acme Corp face?",
        answer_summary="Top 3 customers account for 41% of ARR.",
        source_paragraph_index=2,
        relevant_keywords=["41%", "ARR", "customer concentration", "top three"],
        graded_relevance={0: 0, 1: 0, 2: 2},
    ),
    GoldenQA(
        question="What EU regulatory risk affects Acme Corp and what is the estimated margin impact?",
        answer_summary="Digital Markets Act could compress margins by 3-5 percentage points.",
        source_paragraph_index=2,
        relevant_keywords=["Digital Markets Act", "EU", "3 to 5 percentage points", "margin"],
        graded_relevance={0: 0, 1: 0, 2: 2},
    ),
    GoldenQA(
        question="How do rising interest rates affect Acme Corp's DCF valuation?",
        answer_summary="Each 100bps increase in rates reduces intrinsic value by $6 per share.",
        source_paragraph_index=2,
        relevant_keywords=["$6 per share", "100 basis points", "WACC", "intrinsic value"],
        graded_relevance={0: 1, 1: 0, 2: 2},  # P0 also mentions DCF/WACC/intrinsic value
    ),
    GoldenQA(
        question="What are the main risk factors for investing in Acme Corp?",
        answer_summary="Customer concentration, EU regulatory risk, and interest rate sensitivity.",
        source_paragraph_index=2,
        relevant_keywords=["customer concentration", "regulatory", "interest rates", "risk"],
        graded_relevance={0: 0, 1: 0, 2: 2},
    ),
]
