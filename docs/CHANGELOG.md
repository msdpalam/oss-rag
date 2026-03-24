# OSS RAG Stack — Changelog

All notable changes to this project are documented here in chronological build order.

---

## v0.1.0 — Foundation: Basic RAG Stack

**Theme:** Get a working end-to-end RAG pipeline running locally with no cloud dependencies.

### Infrastructure
- Docker Compose stack: FastAPI backend · React/TypeScript frontend · PostgreSQL · MinIO (S3-compatible) · Qdrant
- All services containerised; single `docker compose up` to run the full stack
- Environment-driven configuration via pydantic-settings and `.env`
- Structured logging with structlog throughout

### Backend
- FastAPI application with lifespan-managed startup/shutdown
- CORS middleware, GZip middleware
- `/health` endpoint with database connectivity check
- `/documents` router: upload, list, delete, status tracking
- `/sessions` router: CRUD, message history per session
- `/chat/stream` SSE endpoint + `/chat` non-streaming JSON endpoint
- PostgreSQL models: `Session`, `Message`, `Document`, `DocumentChunk`
- MinIO client for raw document storage (S3-compatible)
- Async SQLAlchemy with asyncpg driver

### Document Ingestion
- PDF parsing via PyMuPDF + pymupdf4llm (Markdown extraction)
- DOCX, PPTX, XLSX parsing via Unstructured
- HTML, Markdown, plain text support
- Image extraction from PDFs with Claude Vision captioning (concurrency-limited)
- RecursiveCharacterTextSplitter: 512-char chunks, 64-char overlap
- Dense embedding via sentence-transformers `all-MiniLM-L6-v2` (384-dim, CPU)
- Batch embedding with async thread-pool (non-blocking event loop)
- Qdrant upsert: dense vectors + metadata payload per chunk
- PostgreSQL chunk records for metadata queries

### Retrieval & Generation
- Query → embed → Qdrant dense cosine search → top-K chunks
- Claude (claude-sonnet-4-6) answer generation with retrieved context
- Non-streaming RAG pipeline, single-turn

### Frontend
- React 18 + TypeScript + Tailwind CSS + Vite
- Chat interface with message bubbles
- Document upload with drag-and-drop, status polling
- Session sidebar with history
- Citations panel showing retrieved chunks (source, page, score)

---

## v0.2.0 — Chunking & Embedding Robustness

**Theme:** Fix quality issues with the ingestion pipeline that produced poor chunks and near-truncation at the embedding model's token limit.

### Ingestion improvements
- Added `MIN_CHUNK_CHARS = 50` — discards heading-only and whitespace-only fragments
- Extended `TEXT_SPLITTER` separators: added `"? "`, `"! "`, `"; "` for better sentence-aware splitting
- Image captions now pass through the splitter (previously stored whole; at 900+ chars they hit the 256-token model limit)
- Large tables (> 2× `CHUNK_SIZE`) now split; small tables kept whole to preserve structure
- `CHUNK_OVERLAP` increased from 64 → 128 characters (25% of chunk size) to reduce context loss at boundaries
- `RETRIEVAL_TOP_K` default increased from 5 → 8

### Result
- Chunk count increased ~20% (1136 → 1358 for a 340-page PDF) due to better coverage of image content
- Eliminated near-truncation risk for image caption chunks

---

## v0.3.0 — Chat Mode Toggle

**Theme:** Make the LLM behaviour configurable per-request between strict document grounding and full expert knowledge.

### New capability
- **Strict RAG mode** (`strict_rag`): agent answers only from indexed documents; refuses to use general knowledge
- **Expert + Context mode** (`expert_context`): full LLM expertise + documents as grounding context — analogous to GitHub Copilot Chat

### Backend
- `CHAT_MODE` setting (default: `expert_context`)
- Two named system prompts: `STRICT_RAG_PROMPT`, `EXPERT_CONTEXT_PROMPT`
- `mode` parameter added to `ChatRequest`; per-request override of the default
- `stream_answer()` and `answer()` on `ClaudeClient` accept optional `mode` param

### Frontend
- Mode toggle buttons in ChatView header: **Expert + Context** (indigo) and **Strict RAG** (amber)
- `ChatMode` type exported from `types/index.ts`
- `EmptyState` component adapts text and colour to active mode
- Mode sent with every chat request

---

## v0.4.0 — Agentic Architecture

**Theme:** Replace the single-turn RAG pipeline with a multi-step agentic workflow: Claude plans, the orchestrator executes tools, Claude synthesises.

### Architecture change
- Replaced direct RAG pipeline with `AgentOrchestrator` using Claude's native `tool_use` API
- Planner/Executor pattern: non-streaming tool rounds (fast) → streaming final answer (best UX)
- Domain-configurable system prompts via `AGENT_DOMAIN` env var (`stock_analysis` | `general`)
- `AGENT_MAX_STEPS = 8` cap on tool-call rounds per request

### Tools abstraction
- `BaseTool` abstract class with `name`, `description`, `parameters`, `execute()`, `to_claude_schema()`
- `default_tools()` factory returns the active tool set

### Stock analysis tools (4)
| Tool | Data source | Key outputs |
|---|---|---|
| `search_documents` | Qdrant dense search | Relevant excerpts from uploaded files with citations |
| `get_stock_price` | yfinance | OHLCV, period high/low, change%, recent sessions |
| `get_fundamentals` | yfinance | P/E, P/B, EV/EBITDA, revenue growth, margins, FCF, debt ratios, analyst consensus |
| `technical_analysis` | yfinance + pandas | RSI-14, MACD(12,26,9), Bollinger Bands(20,2), SMA 20/50/200, EMA 12/26, ATR-14, OBV trend, support/resistance, overall trend signal |

### Memory
- `WorkingMemory` per-request dataclass: tool call records (step, name, input, result), RAG chunk accumulator with deduplication
- Conversation memory via PostgreSQL message history (last 10 turns loaded as context)

### Streaming SSE protocol (new events)
```
session     → { session_id, message_id }
tool_call   → { tool, input, step }
tool_result → { tool, result, step }
delta       → { text }
done        → { latency_ms, steps, chunks }
error       → { message }
```

### Frontend
- `TOOL_LABELS` map for human-readable tool names
- Tool activity indicator bar (animated Wrench icon) while a tool is running
- Citations now sourced from `done` event (not upfront)
- `StreamEvent` type union updated for new event protocol

### Infrastructure
- Upgraded Qdrant server `v1.9.2` → `v1.13.6` (required by qdrant-client 1.17.1 — old server lacked `query_points` endpoint)
- Added `yfinance>=0.2.37` and `pandas>=2.0.0` to requirements
- Added `AGENT_DOMAIN`, `AGENT_MAX_STEPS`, `CHAT_MODE` to docker-compose and `.env`

---

## v0.5.0 — Episodic Memory + News Tool

**Theme:** Give the agent memory of its own past analyses and access to live news headlines, enabling temporal comparison ("RSI was 45 three days ago, now it's 40 — bearish drift").

### New tools (2)
| Tool | What it does |
|---|---|
| `get_stock_news` | yfinance `.news` property — returns up to 15 articles with date, headline, source, URL. No API key. |
| `recall_past_analyses` | Searches the episodic memory collection for semantically similar past analyses. Optional ticker filter. Returns prior conclusions, dates, tools used. |

### Episodic memory system
- Separate Qdrant collection `"episodes"` (does not touch the `"documents"` collection)
- `EpisodicMemoryStore` with `ensure_collection()`, `store()`, `search()`, `count()`
- Episode embedding: `question + tickers + answer[:600]` — covers both topic and conclusion
- Payload stored: session_id, question, answer_summary, full_answer, tickers, tools_used, timestamp, date_str
- Score threshold: 0.35 for recall (permissive — prefer recall over precision for memory)
- Auto-stored after every streaming or JSON response that analysed at least one ticker

### Agent behaviour change
- Domain system prompt updated with 8-step analysis checklist:
  1. `recall_past_analyses` — check memory first
  2. `get_stock_price`
  3. `technical_analysis`
  4. `get_fundamentals`
  5. `get_stock_news`
  6. `search_documents`
  7–8. Synthesise with bull/bear case + cite sources

### Backend wiring
- `orchestrator.py` `done` event now includes `tickers_analyzed` and `tools_used`
- `chat.py` fires `episodic_memory.store()` after streaming completes (fire-and-forget, non-blocking)
- `main.py` calls `episodic_memory.ensure_collection()` at startup
- `tools/__init__.py` `default_tools()` updated: RecallAnalysesTool first (encourages memory check), StockNewsTool last

### Frontend
- New tool label entries: `get_stock_news` → "Fetching news headlines", `recall_past_analyses` → "Checking memory"

---

## v0.6.0 — Phase 1: Retrieval Quality

**Theme:** Systematic improvement of retrieval precision and recall. Dense-only search is weak on exact terms (ticker symbols, numbers, named entities). Three complementary upgrades applied.

### 1. Hybrid Search — BM25 + Dense via RRF Fusion
- **Problem:** `all-MiniLM-L6-v2` dense embeddings are poor at exact keyword matching — searching "AAPL revenue" may miss chunks that literally contain "AAPL" and "revenue" if the semantic angle is off.
- **Solution:** BM25 sparse encoding runs in parallel with dense encoding. Qdrant fuses both branches via Reciprocal Rank Fusion (RRF).
- Custom `core/sparse_embedder.py` — pure Python, no new dependencies:
  - FNV-1a stable hash → token indices (131 072-dim vocabulary)
  - BM25-TF saturation weighting (k1=1.2, length-normalised)
  - Symmetric: same function for documents at index time and queries at search time
- Qdrant `query_points` with two `Prefetch` branches (dense limit 20, sparse limit 20) → RRF fusion → final top-K
- Fallback to dense-only when `USE_HYBRID_SEARCH=false` or sparse vector is empty
- Ingestion updated: BM25 sparse vectors computed for every chunk alongside dense vectors
- Existing documents: re-indexed to add sparse vectors (re-index via `/documents/{id}/reindex`)

### 2. CrossEncoder Re-ranking
- **Problem:** Bi-encoder retrieval (dense or hybrid) ranks by approximate similarity; highly relevant passages can rank below average ones when surface forms differ.
- **Solution:** Retrieve 20 candidates from Qdrant, then score every `(query, passage)` pair jointly using a CrossEncoder. Return top 6.
- `core/reranker.py` — `CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')` from sentence-transformers (already installed, ~86 MB)
- Runs in a dedicated thread pool (non-blocking event loop)
- Raw logits normalised to [0, 1] via sigmoid for consistent citation score display
- Loaded at startup with graceful degradation if model unavailable
- Configurable: `USE_RERANKING`, `RERANK_CANDIDATES` (default 20), `RERANKER_MODEL`

### 3. HyDE — Hypothetical Document Embeddings (optional, off by default)
- **Problem:** Question embeddings and answer-passage embeddings occupy different semantic regions — "What was Apple's Q3 revenue?" vs "Apple's Q3 revenue was $81.8B..."
- **Solution:** Ask Claude to generate a short hypothetical answer (2-4 sentences), embed that instead of the raw question. The hypothesis embedding is geometrically closer to actual answer passages.
- Implemented in `RAGTool._generate_hypothesis()` — one non-streaming Claude call, falls back to original query on failure
- Enabled via `USE_HYDE=true` in `.env`; off by default to preserve latency

### New config flags
| Flag | Default | Description |
|---|---|---|
| `USE_HYBRID_SEARCH` | `true` | Dense + BM25 sparse via RRF |
| `USE_RERANKING` | `true` | CrossEncoder second-pass |
| `RERANK_CANDIDATES` | `20` | Candidates fetched before reranking |
| `USE_HYDE` | `false` | Hypothetical answer embedding |
| `HYDE_MAX_TOKENS` | `200` | Max length of hypothetical answer |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | CrossEncoder model |

### Verified in production logs
```
vector_store.hybrid_search  sparse_terms=6  top_k=20
reranker.done               candidates=20   returned=6   top_score=0.999
```

---

## Capability Summary

| Capability | Since |
|---|---|
| Document upload and indexing (PDF, DOCX, PPTX, HTML, images) | v0.1.0 |
| Dense semantic search (Qdrant) | v0.1.0 |
| Streaming SSE responses | v0.1.0 |
| Session and message persistence | v0.1.0 |
| S3-compatible document storage (MinIO) | v0.1.0 |
| Image captioning via Claude Vision | v0.1.0 |
| Improved chunking (sentence-aware, overlap, min-size filter) | v0.2.0 |
| Strict RAG vs Expert + Context mode toggle | v0.3.0 |
| Multi-step agentic tool-use loop | v0.4.0 |
| Live stock price data (yfinance) | v0.4.0 |
| Fundamental analysis (valuation, growth, health) | v0.4.0 |
| Technical analysis (RSI, MACD, Bollinger Bands, SMA/EMA, ATR, OBV) | v0.4.0 |
| Per-request tool activity streaming to UI | v0.4.0 |
| Working memory (tool call trace + RAG chunk accumulation) | v0.4.0 |
| Live news headlines (yfinance) | v0.5.0 |
| Episodic memory (past analyses stored and recalled) | v0.5.0 |
| Temporal comparison across sessions | v0.5.0 |
| BM25 hybrid search (exact keyword + semantic fusion via RRF) | v0.6.0 |
| CrossEncoder re-ranking (20 candidates → top 6) | v0.6.0 |
| HyDE hypothetical document embeddings (optional) | v0.6.0 |
