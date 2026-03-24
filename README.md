# OSS RAG Stack

A cloud-agnostic, multi-step **agentic AI** system for document-grounded research and stock analysis — built as an open-source alternative to the Azure Search + OpenAI Demo pattern, with zero vendor lock-in.

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

Ask a question → the agent plans a multi-step analysis using real tools → streams the answer token by token → stores the analysis in memory for future sessions.

**As a stock analysis agent:**

- Live price, fundamentals, and technical indicators via yfinance (no API key)
- News headlines for market sentiment
- Searches your uploaded research documents (10-Ks, reports, transcripts)
- Recalls past analyses to surface metric drift across sessions

**As a document Q&A system:**

- Upload PDF, DOCX, PPTX, HTML, images
- **Hybrid search** — BM25 keyword + dense semantic, fused via RRF
- **CrossEncoder re-ranking** — precision second-pass over 20 candidates
- **HyDE** (optional) — hypothetical document embedding for abstract queries
- Two modes: strict document-only answers or full expert knowledge + documents

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

First run downloads the embedding model (~90 MB) and CrossEncoder (~86 MB). Subsequent starts are instant.

| Service | URL |
| --- | --- |
| **Chat UI** | <http://localhost:3001> |
| **API docs** | <http://localhost:8001/docs> |
| **Qdrant dashboard** | <http://localhost:6333/dashboard> |
| **MinIO console** | <http://localhost:9001> |

### 3. Index your documents

**Upload via UI**: Open the Chat UI → Documents tab → drag and drop files.

**Bulk ingest from CLI:**

```bash
cp /path/to/docs/*.pdf ./data/
docker compose exec backend python ../../scripts/prepdocs.py --data-dir /app/data
```

Supported formats: PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, PNG, JPG, WEBP.

### 4. Start chatting

Open <http://localhost:3001> and ask questions. Toggle between **Expert + Context** and **Strict RAG** modes in the chat header.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend  React / TypeScript / Tailwind                            │
│  Chat · Mode toggle · Session history · Citations panel             │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ SSE / REST
┌─────────────────────────▼───────────────────────────────────────────┐
│  FastAPI backend                                                     │
│                                                                      │
│  AgentOrchestrator  ──► Claude tool-use loop (max 8 steps)          │
│       │                                                              │
│       ├─► recall_past_analyses  ──► Qdrant episodes collection       │
│       ├─► search_documents      ──► BM25 + Dense → RRF → Rerank     │
│       ├─► get_stock_price       ──► yfinance                        │
│       ├─► get_fundamentals      ──► yfinance                        │
│       ├─► technical_analysis    ──► yfinance + pandas               │
│       └─► get_stock_news        ──► yfinance                        │
│                                                                      │
│  Ingestion:  PDF/DOCX/HTML → chunk → BM25 + embed → Qdrant          │
└──────────┬──────────────────────────────────────────────────────────┘
           │
    ┌──────▼──────┐   ┌────────────────┐   ┌──────────────────────┐
    │ PostgreSQL  │   │     Qdrant     │   │  MinIO (S3)          │
    │ sessions    │   │  documents +   │   │  raw files           │
    │ messages    │   │  episodes      │   │                      │
    └─────────────┘   └────────────────┘   └──────────────────────┘
```

See [`docs/ARCHITECTURE_v1.md`](docs/ARCHITECTURE_v1.md) for full Mermaid diagrams.

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
uvicorn main:app --reload --port 8001
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
│   │   │   └── models.py            # ORM models
│   │   ├── routers/
│   │   │   ├── chat.py              # SSE streaming + JSON chat
│   │   │   ├── documents.py         # upload / list / reindex
│   │   │   ├── sessions.py          # session CRUD + message history
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
│       │   ├── components/          # ChatView, MessageBubble, ...
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

## Roadmap

See [`docs/CHANGELOG.md`](docs/CHANGELOG.md) for the full feature history.

Next:

- [ ] Phase 2: Observability — OpenTelemetry tracing, RAGAS evaluation, feedback buttons
- [ ] Phase 3: Agent improvements — parallel tool calls, structured JSON output, portfolio mode
- [ ] Phase 4: Document intelligence — structured table extraction, incremental re-indexing
- [ ] Phase 5: Auth — JWT-based multi-user support, per-user document namespacing
