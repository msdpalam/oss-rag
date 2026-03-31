# Apex Capital Advisors — Virtual Investment Firm

A cloud-agnostic, self-hosted **multi-agent investment platform** — six named AI analysts specialising in equity research, technical trading, macro strategy, retirement planning, crypto, and portfolio construction. Built on a custom agentic RAG stack as an open-source alternative to the Azure Search + OpenAI Demo pattern, with zero vendor lock-in.

## Stack comparison

| Layer | Azure demo | This project |
| --- | --- | --- |
| LLM | Azure OpenAI GPT-4o | **Claude** (claude-sonnet-4-6) |
| Embeddings | Azure OpenAI Ada-002 | **sentence-transformers** (local, free) |
| Sparse search | Azure AI Search BM25 | **Custom BM25** (pure Python, no deps) |
| Vector search | Azure AI Search | **Qdrant** (Docker) |
| Re-ranking | — | **CrossEncoder** (ms-marco-MiniLM) |
| Agent framework | — | **Custom tool-use loop** (Anthropic SDK) |
| Document parsing | Azure Document Intelligence | **PyMuPDF + Unstructured** |
| Object storage | Azure Blob Storage | **MinIO** (S3-compatible) |
| Chat history | Azure Cosmos DB | **PostgreSQL** |
| Backend | Python / Quart | **Python / FastAPI** |
| Frontend | React (TypeScript) | **React (TypeScript)** |
| Hosting | Azure Container Apps | **Docker Compose / Kubernetes** |

---

## What it does

Ask a question → select a focus area → plans a multi-step investigation using 20 real market data tools → streams the answer token by token → remembers past analyses for the next session.

### Focus Areas

Select your investment area from the dropdown in the chat header. Each area routes to a specialist with a curated tool subset and a tailored system prompt.

| Focus Area | Specialisation | Tools |
| --- | --- | --- |
| **Equity Research** | DCF, fundamentals, earnings, insider/institutional signals, peer comparison | 11 |
| **Technical Analysis** | Price action, options flow, market breadth, momentum indicators | 6 |
| **Macro & Economics** | Yield curve, sector rotation, economic indicators, top-down | 7 |
| **Retirement Planning** | Low-beta quality, dividends, tax-advantaged strategy, retirement projections, portfolio P&L | 10 |
| **Crypto & Digital Assets** | Crypto prices (CoinGecko), crypto ETFs (IBIT, FBTC), on-chain news | 6 |
| **Portfolio Strategy** | Screening, allocation, live P&L summary, correlation, position sizing | 10 |
| **All Areas** | Routes to the best specialist automatically | 20 |

### Market Intelligence (20 tools, no API key needed)

Live price · Fundamentals · Technical analysis (RSI, MACD, BB, ATR, OBV) · Options chain · Earnings history · Insider transactions · Institutional holdings · Sector performance · Stock screener · Market breadth · Analyst upgrades · DCF valuation · Peer comparison · Economic indicators · News headlines · Crypto prices (CoinGecko) · Virtual portfolio P&L · Retirement calculator · Episodic memory · Document search

### Per-User Investor Profile

Set your age, risk tolerance (1–5), investment horizon, goals, portfolio size, and tax-advantaged accounts. Every analyst injects your profile into their recommendations — personalised, not generic.

### Document Intelligence

- Upload PDF, DOCX, PPTX, HTML, images (10-Ks, earnings transcripts, research reports)
- **Hybrid search** — BM25 keyword + dense semantic, fused via RRF
- **CrossEncoder re-ranking** — precision second-pass over 20 candidates
- **HyDE** (optional) — hypothetical document embedding for abstract queries
- Strict document-only mode or full expert knowledge + documents

---

## Quick start

### Prerequisites

- Docker Desktop ≥ 4.x with Compose V2
- An [Anthropic API key](https://console.anthropic.com)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/oss-rag.git
cd oss-rag
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Start the stack

```bash
make up
# or: docker compose up -d
```

Docker pulls images, builds the backend and frontend, runs health checks, and wires up the dependency chain automatically. First run also downloads the embedding model (~90 MB) and CrossEncoder (~86 MB) into a persistent volume — subsequent starts are instant.

| Service | URL | Notes |
| --- | --- | --- |
| **Chat UI** | <http://localhost:3010> | React dev server with hot-reload |
| **API** | <http://localhost:8010> | FastAPI — `/docs` available in dev mode |
| **Qdrant dashboard** | <http://localhost:6333/dashboard> | Vector DB explorer |
| **MinIO console** | <http://localhost:9001> | Object storage browser |
| **Adminer** | <http://localhost:8011> | SQL client — start with `--profile dev-tools` |
| **Everything via Nginx** | <http://localhost:8090> | Production proxy — start with `--profile production` |

### 3. Index your documents

**Upload via UI**: Open the Chat UI → Documents tab → drag and drop files.

**Bulk ingest from CLI:**

```bash
cp /path/to/docs/*.pdf ./data/
docker compose exec backend python ../../scripts/prepdocs.py --data-dir /app/data
```

Supported formats: PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, PNG, JPG, WEBP.

### 4. Start chatting

Open <http://localhost:3010> and ask questions. Select a **Focus Area** and toggle between **Expert + Context** and **Strict RAG** modes in the chat header.

---

## Architecture

### Container topology

`docker compose up -d` starts **7 containers** on a private bridge network (`172.20.0.0/16`). Each service has a fixed IP so containers address each other by name with no port conflicts on the host.

```text
 HOST PORTS                CONTAINER              IMAGE                        ROLE
 ──────────────────────────────────────────────────────────────────────────────────────
 :3010                     oss-rag-frontend       built ./app/frontend          React / Vite dev server
 :8010                     oss-rag-backend        built ./app/backend           FastAPI + ML models
 :6333 :6334               oss-rag-qdrant         qdrant/qdrant:v1.13.6         Vector DB (REST + gRPC)
 :5440                     oss-rag-postgres       postgres:16-alpine            Chat history + metadata
 :9000 :9001               oss-rag-minio          minio/minio                   S3-compatible object store
 (one-shot)                oss-rag-minio-init     minio/mc                      Bucket + CORS bootstrap
 :8090 (--profile prod)    oss-rag-nginx          nginx:1.27-alpine             Reverse proxy
 :8011 (--profile tools)   oss-rag-adminer        adminer:4.8.1                 Postgres SQL browser
```

### Health-check dependency chain

Docker Compose enforces startup ordering via `depends_on: condition: service_healthy`. Nothing starts in the wrong order, even on a cold first boot:

```text
  qdrant ──────────────────────────────────────┐
  postgres ─────────────────────────────────── ├──► backend (healthy) ──► frontend
  minio ──► minio-init (buckets + user) ───────┘
```

The backend only starts once Qdrant, Postgres, and MinIO are all reporting healthy. The frontend waits for the backend. If any dependency is slow (e.g. Postgres fsync on first init) the chain waits automatically.

### Data persistence

Four named Docker volumes survive container restarts, image rebuilds, and `docker compose down`:

| Volume | What it stores |
| --- | --- |
| `qdrant_data` | All vector collections — documents + episodic memory |
| `postgres_data` | All sessions, messages, feedback, document metadata |
| `minio_data` | All raw uploaded document files |
| `backend_model_cache` | Downloaded ML models (embedder ~90 MB, reranker ~86 MB) |

> **Warning:** `docker compose down -v` deletes volumes. Use plain `docker compose down` to preserve data.

### Dev vs production profiles

| Mode | Command | What starts |
| --- | --- | --- |
| Development (default) | `docker compose up -d` | All core services; hot-reload on backend + frontend src |
| With DB browser | `docker compose --profile dev-tools up -d` | + Adminer on `:8011` |
| Production | `docker compose --profile production up -d` | + Nginx reverse proxy on `:8090` |

In development, `./app/backend` and `./app/frontend/src` are bind-mounted as live volumes — code changes reflect immediately without rebuilding images.

### Logical architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend  (oss-rag-frontend · :3010)                                   │
│  Auth · Focus Area dropdown · Investor Profile settings                 │
│  Streaming chat · Markdown + syntax highlighting · Feedback             │
│  Collapsible sidebar · Session history · Document manager · Portfolio   │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │ SSE streaming / REST  (Bearer JWT)
┌─────────────────────────▼───────────────────────────────────────────────┐
│  Backend  (oss-rag-backend · :8010)                                     │
│                                                                          │
│  JWT Auth  ──► per-user data isolation (sessions, docs, RAG)            │
│  FIRM_MODE  ──► finance-only domain guardrail on every request          │
│                                                                          │
│  AgentOrchestrator(agent_id, investor_profile, user_id)                 │
│    ──► routes to 1 of 6 focus areas with specialised prompt + tools     │
│    ──► injects client profile into system prompt                        │
│    ──► Claude tool-use loop (max 8 steps)  +  OTel spans                │
│       │                                                                  │
│       ├─ recall_past_analyses  ──► Qdrant episodes collection            │
│       ├─ search_documents      ──► BM25 + Dense → RRF → CrossEncoder    │
│       ├─ get_stock_price / get_fundamentals / technical_analysis        │
│       ├─ get_options_chain / get_earnings_history / get_insider_...     │
│       ├─ get_sector_performance / screen_stocks / get_market_breadth    │
│       ├─ get_analyst_upgrades / calculate_dcf / compare_stocks          │
│       ├─ get_economic_indicators / get_stock_news    all via yfinance   │
│       ├─ get_crypto_data        ──► CoinGecko free API + yfinance ETFs  │
│       ├─ get_portfolio_summary  ──► live P&L on user's positions        │
│       └─ calculate_retirement   ──► FIRE number + projection table      │
│                                                                          │
│  Ingestion:  PDF/DOCX/HTML → chunk → BM25 + embed → Qdrant             │
└────┬─────────────────────────────────────────────────────────────────────┘
     │
┌────▼──────────────┐  ┌──────────────────────────┐  ┌──────────────────┐
│ PostgreSQL        │  │  Qdrant                  │  │  MinIO (S3)      │
│ (:5440)           │  │  (:6333/:6334)           │  │  (:9000)         │
│ users             │  │  documents collection    │  │  raw files       │
│ investor_profiles │  │  (dense + BM25 sparse)   │  │                  │
│ portfolio_pos.    │  │  episodes collection     │  │                  │
│ sessions          │  │  (past analyses)         │  │                  │
│ messages+feedback │  │                          │  │                  │
│ documents+chunks  │  │                          │  │                  │
└───────────────────┘  └──────────────────────────┘  └──────────────────┘
```

See [`docs/ARCHITECTURE_v1.md`](docs/ARCHITECTURE_v1.md) for full Mermaid diagrams and the microservices decomposition plan.

---

## Developer workflow

```bash
make help          # show all commands
make up            # start full stack
make restart       # rebuild + restart backend after code changes
make logs-be       # tail backend logs
make test-unit     # run unit tests (no services needed)
make test-int      # run integration tests (stack must be running)
make lint          # ruff linter
make format        # ruff auto-format
make shell         # bash into backend container
make reindex DOC_ID=<uuid>  # re-index a specific document
```

### Run backend locally (outside Docker)

```bash
make infra-up       # start postgres, qdrant, minio only

cd app/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn main:app --reload --port 8010
```

### Run frontend locally

```bash
cd app/frontend
npm install && npm run dev
```

---

## Testing

```bash
# Unit tests — pure logic, no services, fast
make test-unit

# Integration tests — real postgres + qdrant (stack must be up)
make test-int

# Coverage report
make test-cov
```

Tests are organised in `app/backend/tests/`:

| Suite | What it tests | Services needed |
| --- | --- | --- |
| `unit/test_sparse_embedder.py` | BM25 tokeniser, FNV hash, encoding | None |
| `unit/test_chunking.py` | Chunk splitting, size filtering, table handling | None |
| `unit/test_memory.py` | WorkingMemory record, dedup, summary | None |
| `unit/test_tools_schema.py` | Tool contract, Claude schema structure | None |
| `integration/test_health.py` | `/health` and `/health/ready` endpoints | Postgres, Qdrant |
| `integration/test_sessions.py` | Sessions list/get, 404 handling | Postgres |
| `integration/test_messages.py` | Feedback endpoint (400/404/422/204, persistence, overwrite) | Postgres |

**Smoke test** (against a live stack, no pytest):

```bash
python scripts/smoke_test.py              # full test including one LLM call
python scripts/smoke_test.py --skip-chat  # fast mode, no API key needed
```

---

## Configuration

All values are set via environment variables. Copy `.env.example` to `.env` and adjust.

### Key feature flags

| Variable | Default | Description |
| --- | --- | --- |
| `USE_HYBRID_SEARCH` | `true` | BM25 + dense search fused via RRF |
| `USE_RERANKING` | `true` | CrossEncoder second-pass (20 candidates → top 6) |
| `RERANK_CANDIDATES` | `20` | Candidates fetched before re-ranking |
| `USE_HYDE` | `false` | Hypothetical document embedding (adds 1 Claude call) |
| `AGENT_DOMAIN` | `stock_analysis` | System prompt domain: `stock_analysis` or `general` |
| `AGENT_MAX_STEPS` | `8` | Max tool-call rounds per request |
| `CHAT_MODE` | `expert_context` | Default: `expert_context` or `strict_rag` |

### Switching embedding models

```bash
# Higher quality, more memory (768-dim)
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
EMBEDDING_DIMENSIONS=768
```

After changing the model, re-index all documents:

```bash
make reset-qdrant  # WARNING: deletes all vectors
# then re-upload documents via the UI
```

### Using GPU for embeddings

```bash
EMBEDDING_DEVICE=cuda   # NVIDIA
EMBEDDING_DEVICE=mps    # Apple Silicon
```

### Replacing MinIO with real S3

```bash
S3_ENDPOINT_URL=        # leave blank for AWS S3
S3_ACCESS_KEY=AKIA...
S3_SECRET_KEY=...
S3_REGION=us-east-1
```

### Production deployment

```bash
docker compose --profile production up -d
# Starts Nginx reverse proxy in addition to all services
```

---

## Project structure

```text
oss-rag/
├── app/
│   ├── backend/
│   │   ├── agents/
│   │   │   ├── orchestrator.py      # tool-use loop, SSE streaming
│   │   │   ├── memory.py            # WorkingMemory per request
│   │   │   └── episodic_memory.py   # Qdrant-backed past analysis store
│   │   ├── core/
│   │   │   ├── config.py            # pydantic-settings
│   │   │   ├── claude_client.py     # Claude API wrapper
│   │   │   ├── embedder.py          # sentence-transformers async
│   │   │   ├── sparse_embedder.py   # BM25 tokeniser (pure Python)
│   │   │   ├── reranker.py          # CrossEncoder re-ranker
│   │   │   ├── vector_store.py      # Qdrant hybrid search
│   │   │   ├── storage.py           # MinIO / S3 client
│   │   │   ├── database.py          # SQLAlchemy async
│   │   │   ├── models.py            # ORM models
│   │   │   └── telemetry.py         # OpenTelemetry setup (no-op when unconfigured)
│   │   ├── routers/
│   │   │   ├── chat.py              # SSE streaming + JSON chat
│   │   │   ├── documents.py         # upload / list / reindex
│   │   │   ├── sessions.py          # session CRUD + message history
│   │   │   ├── messages.py          # feedback endpoint
│   │   │   └── health.py            # liveness + readiness
│   │   ├── tools/
│   │   │   ├── base.py              # BaseTool abstract class
│   │   │   ├── rag_tool.py          # search_documents (hybrid + rerank)
│   │   │   ├── stock_data.py        # get_stock_price, get_fundamentals
│   │   │   ├── technical.py         # technical_analysis
│   │   │   ├── news_tool.py         # get_stock_news
│   │   │   └── recall_tool.py       # recall_past_analyses
│   │   ├── utils/
│   │   │   └── ingestion.py         # parse → chunk → embed → index
│   │   ├── tests/
│   │   │   ├── unit/                # pure logic, no services
│   │   │   └── integration/         # real postgres + qdrant, mocked ML
│   │   ├── main.py                  # FastAPI app + lifespan
│   │   ├── requirements.txt
│   │   ├── requirements-dev.txt
│   │   └── pyproject.toml           # pytest + ruff config
│   └── frontend/
│       ├── src/
│       │   ├── components/          # ChatView, MessageBubble, HelpModal, MarkdownContent, ...
│       │   ├── api/client.ts        # typed API + SSE client
│       │   └── types/index.ts       # shared TypeScript types
│       └── Dockerfile
├── docs/
│   ├── ARCHITECTURE_v1.md           # Mermaid architecture diagrams
│   └── CHANGELOG.md                 # Feature history by version
├── infra/
│   ├── postgres/init.sql
│   ├── qdrant/config.yaml
│   └── nginx/
├── scripts/
│   └── prepdocs.py                  # CLI bulk document ingestion
├── .github/workflows/ci.yml         # lint → unit → integration → build
├── Makefile                         # developer operations
├── docker-compose.yml
└── .env.example
```

---

## CI / CD

CI runs automatically on push to `main` / `develop` and on pull requests:

| Job | What it checks | Services |
| --- | --- | --- |
| **Lint** | ruff linter + format | none |
| **Unit tests** | Pure logic tests | none |
| **Integration tests** | API endpoints | Postgres + Qdrant |
| **Build** | Docker image builds successfully | none |

CD (deploy on merge to main) is planned for a future iteration.

---

## What we've built

See [`docs/CHANGELOG.md`](docs/CHANGELOG.md) for the full version history and [`docs/ARCHITECTURE_v1.md`](docs/ARCHITECTURE_v1.md) for system diagrams.

| Phase | Theme | Status |
| --- | --- | --- |
| v0.1 | Foundation — Docker stack, RAG pipeline, SSE streaming, session history | ✅ Done |
| v0.2 | Chunking robustness — sentence-aware splitting, min-size filter, overlap | ✅ Done |
| v0.3 | Chat modes — Strict RAG vs Expert + Context toggle | ✅ Done |
| v0.4 | Agentic architecture — tool-use loop, stock analysis tools, working memory | ✅ Done |
| v0.5 | Episodic memory — past-analysis recall, news tool, temporal comparison | ✅ Done |
| v0.6 | Retrieval quality — BM25 hybrid search, CrossEncoder re-ranking, HyDE | ✅ Done |
| v0.7 | Observability & UX — onboarding modal, feedback buttons, OpenTelemetry, smoke tests | ✅ Done |
| v0.8 | Rich formatting — Markdown rendering, syntax-highlighted code, Tailwind Typography | ✅ Done |

## Roadmap

### Phase 3 — Agent Intelligence

- [ ] **Parallel tool calls** — fan out multiple tools in a single Claude response (e.g. price + technicals + news simultaneously); cut multi-tool latency by ~60%
- [ ] **Structured output mode** — JSON-schema-validated responses for chart data, comparison tables, portfolio summaries
- [ ] **Tool result caching** — TTL cache on stock data tools; avoid redundant yfinance calls within a session
- [ ] **Portfolio mode** — analyse a basket of tickers in one request; cross-asset correlation and relative strength

### Phase 4 — Document Intelligence

- [ ] **Table extraction as DataFrames** — detect and parse tables into structured data; allow Claude to run calculations against them
- [ ] **Incremental re-indexing** — diff-based re-index; only re-embed changed pages rather than the whole document
- [ ] **Document versioning** — track document revisions; surface "Q3 revenue changed from $X to $Y" automatically
- [ ] **Multi-modal queries** — accept image input alongside text; analyse charts, screenshots, and scanned documents

### Phase 5 — Multi-User & Auth

- [ ] **JWT authentication** — secure login, per-user sessions and document namespaces
- [ ] **Team sharing** — share document collections and sessions across a workspace
- [ ] **Role-based access** — reader / analyst / admin roles; per-document visibility controls
- [ ] **Usage metering** — track token consumption and document storage per user

### Phase 6 — Microservices Decomposition

The current monolithic FastAPI backend is intentionally simple for local development. As load scales, each concern can be extracted into its own service:

```text
┌─────────────┐   ┌──────────────────┐   ┌─────────────────────┐
│  API Gateway │──►│  Chat Service    │──►│  Agent Orchestrator  │
│  (Nginx /   │   │  (FastAPI SSE)   │   │  (stateless worker) │
│   Traefik)  │   └──────────────────┘   └─────────────────────┘
└─────────────┘
       │           ┌──────────────────┐   ┌─────────────────────┐
       ├──────────►│ Ingestion Worker  │   │  Embedding Service  │
       │           │ (Celery / ARQ)   │──►│  (model server,     │
       │           └──────────────────┘   │   swappable)        │
       │                                  └─────────────────────┘
       │           ┌──────────────────┐   ┌─────────────────────┐
       └──────────►│ Documents API    │   │  Reranker Service   │
                   │ (upload / list)  │   │  (CrossEncoder,     │
                   └──────────────────┘   │   GPU-accelerated)  │
                                          └─────────────────────┘
```

Each service is independently deployable, scalable, and replaceable:

- **Swap the embedding model** without touching the chat service
- **Scale the ingestion worker** independently during bulk uploads
- **GPU reranking** on a dedicated node without co-locating with the API
- **Message broker** (Redis Streams / RabbitMQ) for async ingestion pipeline
- **Kubernetes + HPA** for auto-scaling chat workers under load

### Phase 7 — Evaluation & Quality

- [ ] **RAGAS evaluation** — automated faithfulness, answer relevancy, context precision/recall metrics on a golden test set
- [ ] **Retrieval A/B testing** — compare BM25-only vs hybrid vs HyDE on real query logs
- [ ] **Answer quality dashboard** — visualise feedback signals (thumbs up/down), latency, token cost per query
- [ ] **Hallucination detection** — flag low-grounding responses before they reach the user

### Phase 8 — Advanced Capabilities

- [ ] **Web search tool** — real-time search (Brave / Serper) as an agent tool alongside document search
- [ ] **Code execution** — sandboxed Python interpreter for data analysis on uploaded CSVs / Excel files
- [ ] **Scheduled runs** — nightly portfolio analysis reports delivered via email or Slack
- [ ] **Connector framework** — plug in live data sources (Bloomberg, Refinitiv, internal databases) as first-class tools
