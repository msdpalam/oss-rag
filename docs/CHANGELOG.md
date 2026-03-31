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

## v0.7.0 — Phase 2: Observability & UX

**Theme:** Make the system production-observable and the user experience polished — onboarding flow, response quality feedback, and distributed tracing.

### Onboarding help modal

- Multi-step modal (4 steps: What is this / Features / Chat Modes / Quick Tips)
- Auto-shown on first visit via `localStorage.hasSeenHelp` flag; never shown again after dismissal
- Re-openable via **Help** button (HelpCircle icon) in the chat header
- Step indicator dots with keyboard-accessible navigation; pure Tailwind, no external UI library

### Response feedback

- Thumbs up / thumbs down buttons on every assistant message bubble
- `POST /messages/{id}/feedback` endpoint — `204 No Content`, validates `"up"|"down"` via Pydantic `Literal`
- `feedback` and `feedback_at` columns added to the `messages` table (PostgreSQL + ORM model)
- `GET /sessions/{id}/messages` response now includes `feedback` and `feedback_at` fields
- Frontend initialises button state from persisted feedback on session reload
- Last write wins — feedback can be changed at any time

### OpenTelemetry distributed tracing

- `core/telemetry.py` — `configure_telemetry()` sets up SDK at startup; zero-overhead no-op when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset
- `FastAPIInstrumentor` auto-instruments all HTTP routes (spans for every request)
- `agent.run` span wraps the full tool-use loop (attributes: `session_id`, `mode`)
- `tool.<name>` child span per tool call (attributes: `tool`, `step`)
- gRPC OTLP exporter supports Jaeger, Grafana Tempo, or any OpenTelemetry Collector
- `OTEL_EXPORTER_OTLP_ENDPOINT` added to `.env.example` (commented out)

### New API endpoint

- `GET /sessions/{id}` — fetch single session by ID (was missing; returning 405 previously)

### Testing

- `tests/integration/test_messages.py` — 6 integration tests covering 400 / 404 / 422 error cases, 204 success, persistence verification, and feedback overwrite
- `scripts/smoke_test.py` — standalone end-to-end test agent: 7 checks against a live stack including full chat-stream round-trip, feedback submission, and cleanup; coloured pass/fail output; `--skip-chat` flag for keyless runs

### CI

- GitHub Actions CI verified green across all 4 jobs: lint, unit tests, integration tests, Docker build

---

## v0.8.0 — Rich Markdown Rendering

**Theme:** Make assistant responses look as polished as Claude.ai or ChatGPT — formatted headings, lists, tables, and syntax-highlighted code blocks.

### Frontend changes

- `react-markdown` + `remark-gfm` — full GitHub-Flavored Markdown: headings, lists, tables, blockquotes, strikethrough, task lists
- `react-syntax-highlighter` (Prism, One Dark theme) — code blocks with language label bar
- `@tailwindcss/typography` — `prose prose-sm prose-gray` class for beautiful typographic defaults
- Custom `MarkdownContent.tsx` component replaces raw `whitespace-pre-wrap` div in `MessageBubble`
- Syntax highlighter lazy-loaded via `React.lazy` — initial JS bundle cut from **986 KB → 357 KB** (gzip: 335 KB → 108 KB)
- `<Suspense>` fallback renders plain `<pre>` while highlighter chunk loads (no flash of unstyled content)
- Inline code rendered as indigo pill (`bg-gray-100 text-indigo-700`)
- External links open in new tab with `rel="noopener noreferrer"`
- Streaming cursor preserved: `streaming-cursor` CSS class applied to the prose container during generation
- Tailwind Typography configured for compact chat rhythm (tighter `p`/`li`/`pre` margins)

---

## v0.9.0 — Phase 3: Retrieval Evaluation Suite

**Theme:** Measure what you build. An offline evaluation suite with retrieval metrics and LLM-as-judge answer quality scoring, integrated into CI via `make eval`.

### Evaluation framework
- Ragas-inspired design — no Ragas dependency, fully custom
- `tests/eval/conftest.py` — shared fixtures: test corpus, question set, expected answers
- `tests/eval/test_retrieval_metrics.py` — Recall@K, MRR, NDCG@K against a labelled question set
- `tests/eval/test_answer_quality.py` — LLM-as-judge: faithfulness, answer relevance, context precision
- `make eval` — runs retrieval metrics (no API key required)
- `make eval-llm` — runs full LLM-as-judge eval (requires ANTHROPIC_API_KEY)

---

## v1.0.0 — Phase 4: JWT Auth + Per-User Multi-Tenancy

**Theme:** Secure the stack with email/password authentication and isolate every user's data — sessions, documents, and RAG search results.

### New files
- `core/auth.py` — `hash_password`, `verify_password`, `create_access_token`, `decode_access_token`, `get_current_user` FastAPI dependency
- `routers/auth.py` — `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `contexts/AuthContext.tsx` — React context: user/token state, login/logout/register helpers, localStorage persistence, initial `GET /auth/me` validation
- `components/AuthPage.tsx` — login + signup card (tab toggle, pure Tailwind, no external UI lib)

### Backend changes
- `User` model: added `password_hash VARCHAR(255)` column; `init.sql` updated
- `core/config.py`: `JWT_SECRET_KEY`, `JWT_ALGORITHM="HS256"`, `JWT_EXPIRY_HOURS=24`
- All routers (chat, sessions, documents, messages) require `Bearer` token via `Depends(get_current_user)`
- Per-request `AgentOrchestrator(user_document_ids=...)` — scopes RAG search to current user's indexed documents
- `RAGTool._allowed_document_ids` passed to `vector_store.search()` at query time
- Session and document endpoints filter by `current_user.id` — users see only their own data
- Authorization header changed from required `Header(...)` to optional `Header(None)` with manual check → returns proper `401` instead of `422`

### Frontend changes
- `api/client.ts` — `authHeader()` helper injects `Authorization: Bearer <token>` on every request; 401 response dispatches `auth:logout` DOM event → `AuthContext` listens and clears session automatically
- `App.tsx` — wrapped with `<AuthProvider>`; shows `<AuthPage>` when not authenticated
- `SessionSidebar.tsx` — user display name + logout button; sidebar header renamed to "Stock Analyst"

### New config
```
JWT_SECRET_KEY=change-me-in-production-use-random-32-char-string
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24
```

### Security note
`passlib[bcrypt]` pinned to `<4.0.0` — passlib 1.7.4 is not compatible with bcrypt 4.x.

---

## v1.1.0 — Phase S: Security + UX Hardening

**Theme:** Production-quality security headers, smart scroll, collapsible sidebar, session loading skeleton, and error retry — all shipped as a single polish pass.

### Security (S1–S2)
- **S1 — 401 auto-logout**: `api/client.ts` dispatches `auth:logout` custom DOM event on any 401 response; `AuthContext` listens and clears session immediately — no stale UI after token expiry
- **S2 — nginx security headers**: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Content-Security-Policy` — added to `infra/nginx/conf.d/default.conf`

### UX (U1–U4)
- **U1 — Smart auto-scroll**: `scrollContainerRef` tracks scroll position; only auto-scrolls when within 150px of the bottom — preserves manual scrollback during long responses
- **U2 — Collapsible sidebar**: chevron toggle between expanded (`w-64`) and icon-only (`w-14`) modes; collapsed state shows tooltips on hover
- **U3 — Session loading skeleton**: shimmer rows (4, alternating user/assistant layout) shown while `getMessages()` resolves — eliminates blank flash on session switch
- **U4 — Error retry**: failed chat shows inline error banner with a **Retry** button that restores the input text

### Streaming fix
- `isStreamingRef` (a React ref, not state) guards the session-change `useEffect` — prevents the effect from overwriting the streaming placeholder with stale DB data mid-stream when `onSessionCreated` fires

---

## v1.2.0 — Phase 5: 17 Market Intelligence Tools

**Theme:** Transform the single-tool stock agent into a comprehensive market intelligence platform covering options, earnings, insider activity, institutional flows, macro indicators, DCF, and more.

### New tools (11) in `tools/market_tools.py`
| Tool | Key data | Source |
|---|---|---|
| `get_options_chain` | Put/call ratio, IV by strike, unusual flow | yfinance |
| `get_earnings_history` | EPS beat/miss history, surprise%, next earnings | yfinance |
| `get_insider_transactions` | Insider buys/sells, form 4 data, net conviction | yfinance |
| `get_institutional_holdings` | Top 10 holders, QoQ changes, concentration | yfinance |
| `get_sector_performance` | 9 sector ETF returns (YTD, 1M, 3M), rotation map | yfinance |
| `screen_stocks` | Configurable screener over 50 S&P 500 tickers | yfinance |
| `get_market_breadth` | Advance/decline ratio, new 52w hi/lo, VIX proxy | yfinance |
| `get_analyst_upgrades` | Recent rating changes, PT revisions, consensus | yfinance |
| `calculate_dcf` | Intrinsic value + ±2% growth/WACC sensitivity table | yfinance |
| `compare_stocks` | Side-by-side P/E, EV/EBITDA, margins, growth, target | yfinance |
| `get_economic_indicators` | 10Y/2Y yields, curve, inflation proxy, PMI proxy, DXY | yfinance |

### Orchestrator system prompt overhaul
- Replaced 8-step checklist with 17-step tool selection guide
- Tool selection logic by query type (quick price check vs full recommendation vs screening vs macro)
- Structured output format: BULLISH/BEARISH/NEUTRAL verdict → bull/bear cases → key metrics table → risk factors

### `tools/__init__.py`
- `default_tools()` updated to return all 17 tools
- All 11 new tools exported in `__all__`

### Frontend
- `TOOL_LABELS` map extended to all 17 tools with human-readable activity descriptions

---

## v1.3.0 — Phase A: Virtual Investment Firm

**Theme:** Transform the platform from a generic stock agent into a branded multi-agent investment firm — "Apex Capital Advisors" — with 6 named specialist analysts, per-user investor profiles, and a finance-only domain lock.

### A1 — Investor Profile

**Database**
- New `investor_profiles` table: `user_id` (PK → FK users), `age`, `risk_tolerance` (1–5), `horizon_years`, `goals TEXT[]`, `portfolio_size_usd`, `monthly_contribution_usd`, `tax_accounts TEXT[]`, `preferred_agent`, timestamps
- `init.sql` updated for fresh deployments

**API**
- `routers/profile.py`: `GET /profile` (returns empty defaults if not set), `PUT /profile` (upsert with validation — goals, tax_accounts, preferred_agent sanitised to valid values)
- Registered at `/profile` in `main.py`

**ORM**
- `InvestorProfile` model added to `core/models.py`

### A2 — Domain Lock (FIRM_MODE)

- `FIRM_MODE: bool = True`, `FIRM_NAME: str = "Apex Capital Advisors"` in `core/config.py`
- `_FIRM_GUARDRAIL` block prepended to every system prompt when `FIRM_MODE=True`
- Off-topic questions receive: *"I'm a specialized investment analyst at Apex Capital Advisors and can only assist with finance and investment topics."*
- Finance scope: stocks, bonds, ETFs, options, crypto, commodities, macro economics, sector analysis, portfolio management, retirement planning, tax-advantaged accounts, REITs

### A3 — 6 Named Analyst Personas

All defined in `_PERSONAS` dict in `agents/orchestrator.py`. `AgentOrchestrator` now accepts `agent_id` and `investor_profile`.

| ID | Character | Title | Tool subset | Specialisation |
|---|---|---|---|---|
| `equity_analyst` | Alex | Equity Analyst | 11 tools | DCF, fundamentals, earnings, insiders, peer comparison |
| `technical_trader` | Morgan | Technical Trader | 6 tools | Price action, options flow, market breadth |
| `macro_strategist` | Jordan | Macro Strategist | 7 tools | Yield curve, sector rotation, economic indicators |
| `retirement_planner` | Riley | Retirement Planner | 8 tools | Low-beta quality, dividend stability, tax strategy |
| `crypto_analyst` | Sam | Crypto Analyst | 5 tools | Crypto ETFs (IBIT, FBTC), on-chain news, risk sentiment |
| `portfolio_strategist` | Casey | Portfolio Strategist | 9 tools | Screening, allocation, correlation, position sizing |
| `auto` | Apex AI | Investment Analyst | 17 tools | Best-match routing — all capabilities |

**Investor profile injection**: `_PROFILE_TEMPLATE` is prepended to the active system prompt when profile data is available (age, risk tolerance, horizon). Every recommendation is personalised to the client's specific situation.

**`chat.py` changes**
- `ChatRequest` gains `agent_id: Optional[str] = None`
- Both `/chat/stream` and `/chat` fetch the investor profile via `_get_investor_profile()` and pass it to `AgentOrchestrator`
- `session` SSE event now includes `agent_id`, `agent_character`, `agent_title`
- `done` SSE event also includes agent identity fields

### A4 — Settings UI

- New `SettingsPage.tsx` — modal overlay:
  - **Age**: range slider 18–80
  - **Risk tolerance**: 5 color-coded labeled cards (Very Conservative → Aggressive)
  - **Goals**: checkboxes (Retirement, Growth, Income, Capital Preservation)
  - **Investment horizon**: range slider 1–40 years
  - **Portfolio size** + **Monthly contribution**: number inputs
  - **Tax-advantaged accounts**: checkboxes (401k, Roth IRA, Traditional IRA, Taxable Brokerage)
  - Loads `GET /profile` on open; saves via `PUT /profile`
- Settings icon ("Investor Profile") added to `SessionSidebar` bottom nav

### A5 — Agent Selector UI

- `AgentSelector` component (in `ChatView.tsx`): 7 colored horizontal pills above the chat input
  - Auto (gray), Alex (blue), Morgan (violet), Jordan (emerald), Riley (teal), Sam (orange), Casey (rose)
- `selectedAgent` state sent as `agent_id` in every `streamChat` call
- `StreamingMessage` and `Message` types extended with `agent_id`, `agent_character`, `agent_title`
- `MessageBubble` displays agent character + title above each assistant response (e.g., "Alex — Equity Analyst")
- Avatar circle shows agent initial instead of generic bot icon

### New `types/index.ts` exports
- `AgentId` — union type of all valid agent IDs
- `InvestorProfile` — profile shape matching `GET /profile` response
- `ChatRequest.agent_id` — optional agent selector field

---

## v1.4.0 — Phase B: Market Data Expansion + Virtual Portfolio

**Theme:** Add three new specialist tools (20 total), a virtual portfolio tracker with full CRUD UI, and a retirement planner — completing the Apex Capital Advisors feature set.

### B1 — CryptoTool (`get_crypto_data`)

- `tools/crypto_tool.py`: `CryptoTool.execute(symbols: List[str])` — mixed crypto/ETF resolver
- 20-coin `_SYMBOL_TO_ID` map → CoinGecko free API (`/simple/price`) — no API key required
- Crypto ETFs (`IBIT`, `FBTC`, `GBTC`, `ARKB`, `BITB`) → yfinance `fast_info` instead
- Returns: price (USD), 24h change %, market cap (B), 24h volume (B) per coin
- Assigned to Sam (Crypto Analyst) persona exclusively; also available in auto mode

### B2 — Virtual Portfolio Tracker (`get_portfolio_summary`)

#### Database

- New `portfolio_positions` table: `id`, `user_id` (FK users, CASCADE), `ticker`, `asset_type` (stock/etf/crypto_etf/crypto), `shares` (NUMERIC 18,6), `avg_cost_usd` (NUMERIC 18,4), `notes`, timestamps
- Unique index on `(user_id, ticker)` — upsert merges shares with weighted average cost

#### API (`routers/portfolio.py`)

- `GET /portfolio` — list all positions for current user
- `POST /portfolio/positions` — add position (upserts with weighted avg if ticker exists)
- `PUT /portfolio/positions/{id}` — update shares / avg cost / notes
- `DELETE /portfolio/positions/{id}` — remove position

#### Tool (`tools/portfolio_tool.py`)

- `PortfolioSummaryTool._user_id` injected by `AgentOrchestrator` at construction time
- Reads DB via `AsyncSessionLocal()` directly; fetches live prices via yfinance
- Output: full position table with P&L, allocation %, portfolio totals, best/worst performers
- Assigned to Casey (Portfolio Strategist) and Riley (Retirement Planner); also auto

#### Frontend (`components/PortfolioView.tsx`)

- Position table: ticker, asset type, shares, avg cost, cost basis, notes, delete button
- Collapsible "Add Position" form: ticker, asset type (dropdown), shares, avg cost, notes
- Empty state with prompt to ask Casey for live P&L analysis
- Refresh button, loading spinner, error display
- "Portfolio" nav item added to `SessionSidebar` bottom nav (TrendingUp icon)
- Wired into `App.tsx` as third view alongside Chat and Documents

### B3 — Retirement Calculator (`calculate_retirement`)

- `tools/retirement_tool.py`: `RetirementCalculatorTool.execute(...)`
- Parameters: `annual_expenses`, `current_portfolio` (default 0), `monthly_contribution` (default 0), `annual_return_pct` (default 7.0), `inflation_pct` (default 3.0), `years` (optional custom horizon)
- Computes: FIRE number (25× expenses), current progress %, years-to-FIRE (binary search), required monthly contribution, projection table (5/10/15/20/25/30yr + custom), sensitivity table (±2% return)
- Assigned to Riley (Retirement Planner); also available in auto mode

### Tool label updates

- `ChatView.tsx` `TOOL_LABELS` extended with `get_crypto_data`, `get_portfolio_summary`, `calculate_retirement`

### Persona tool count updates (final)

| ID | Character | Tools |
| --- | --- | --- |
| `equity_analyst` | Alex | 11 |
| `technical_trader` | Morgan | 6 |
| `macro_strategist` | Jordan | 7 |
| `retirement_planner` | Riley | 10 (+`calculate_retirement`, `get_portfolio_summary`) |
| `crypto_analyst` | Sam | 6 (+`get_crypto_data`) |
| `portfolio_strategist` | Casey | 10 (+`get_portfolio_summary`) |
| `auto` | Apex AI | 20 (all tools) |

---

## v1.4.1 — UX Refinements + Port Isolation

### Focus Area dropdown (UX)

- Replaced 7 agent selector pills above the chat input with a **"Focus Area"** labeled `<select>` dropdown in the header bar, alongside the Mode toggle
- Labels changed from character names (Alex, Morgan…) to investment domain names: All Areas, Equity Research, Technical Analysis, Macro & Economics, Retirement Planning, Crypto & Digital Assets, Portfolio Strategy
- Internal persona routing unchanged — only the display layer updated
- Message bubbles now show the focus area label (e.g. "Equity Research") instead of "Alex — Equity Analyst"
- Chat area gains one full row of vertical space

### Port reconfiguration

All host-side ports scanned against sibling projects under `~/tutorials/ai-ml/gen-ai/` and reassigned to an isolated **8010/3010 band**:

| Service | Old port | New port | Conflict resolved |
| --- | --- | --- | --- |
| Backend API | 8001 | **8010** | — |
| Frontend UI | 3001 | **3010** | HomeByMeer Grafana (3001) |
| Nginx reverse proxy | 80 | **8090** | system port, multiple apps |
| Adminer | 8080 | **8011** | HomeByMeer Keycloak (8080) |
| PostgreSQL (host) | 5433 | **5440** | aegis-realty-ai (5433) |

Internal Docker network ports (container-to-container) unchanged.

### Test fixes

- `test_tools_schema.py` expanded from 6 → 20 tools; new schema tests for `CryptoTool`, `PortfolioSummaryTool`, `RetirementCalculatorTool`
- Integration `conftest.py` registers a CI test user on startup and injects `Authorization: Bearer` into all requests — fixes 401s on all protected endpoints
- `smoke_test.py` rewritten to include auth, profile, and portfolio CRUD checks (10 test sections)
- `ci.yml` — added `JWT_SECRET_KEY` to integration test env

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
| Onboarding help modal (multi-step, auto-show once, re-openable) | v0.7.0 |
| Response feedback (thumbs up/down, persisted to DB) | v0.7.0 |
| OpenTelemetry distributed tracing (FastAPI + agent + tool spans) | v0.7.0 |
| End-to-end smoke test agent (`scripts/smoke_test.py`) | v0.7.0 |
| Rich Markdown rendering (headings, lists, tables, code) | v0.8.0 |
| Syntax-highlighted code blocks (Prism, One Dark, lazy-loaded) | v0.8.0 |
| Retrieval evaluation suite (Recall@K, MRR, NDCG@K, LLM-as-judge) | v0.9.0 |
| Email/password auth with JWT (register, login, auto-logout on 401) | v1.0.0 |
| Per-user data isolation (sessions, documents, RAG search) | v1.0.0 |
| nginx security headers (CSP, X-Frame-Options, nosniff, Referrer) | v1.1.0 |
| Smart auto-scroll (preserves manual scrollback) | v1.1.0 |
| Collapsible sidebar (icon-only mode) | v1.1.0 |
| Session loading skeleton + error retry with text restore | v1.1.0 |
| Options chain (put/call ratio, IV, unusual flow) | v1.2.0 |
| Earnings history (EPS beat/miss cadence, surprise%, next date) | v1.2.0 |
| Insider transactions (Form 4, net conviction signal) | v1.2.0 |
| Institutional holdings (top 10 holders, QoQ changes) | v1.2.0 |
| Sector performance (9 sector ETFs, rotation map) | v1.2.0 |
| Stock screener (configurable filters over S&P 500 sample) | v1.2.0 |
| Market breadth (advance/decline, new 52w hi/lo, VIX proxy) | v1.2.0 |
| Analyst upgrades (rating changes, PT revisions, consensus) | v1.2.0 |
| DCF valuation (intrinsic value + growth/WACC sensitivity table) | v1.2.0 |
| Peer comparison (side-by-side valuation, growth, margins) | v1.2.0 |
| Economic indicators (yield curve, inflation, PMI proxy, DXY) | v1.2.0 |
| Finance-only domain lock (FIRM_MODE — off-topic redirect) | v1.3.0 |
| 6 named analyst personas with specialised prompts + tool subsets | v1.3.0 |
| Per-user investor profile (age, risk, horizon, goals, portfolio) | v1.3.0 |
| Investor profile injected into every agent system prompt | v1.3.0 |
| Investor Profile settings UI (sliders, cards, checkboxes) | v1.3.0 |
| Agent selector pills (Auto, Alex, Morgan, Jordan, Riley, Sam, Casey) | v1.3.0 |
| Agent identity shown on every assistant message bubble | v1.3.0 |
