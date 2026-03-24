# OSS RAG Stack — Solution Architecture v1

> Stack: FastAPI · React/TypeScript · Claude (Anthropic) · Qdrant · PostgreSQL · MinIO · Docker Compose
> Domain: Multi-step Agentic Stock Analysis with Hybrid RAG and Episodic Memory

---

## 1. System Overview

```mermaid
graph TB
    subgraph Frontend["Frontend — React / TypeScript / Tailwind (port 3001)"]
        Chat["Chat View\n• Streaming SSE\n• Mode toggle: Expert / Strict RAG\n• Tool activity indicator"]
        Docs["Document Manager\n• Upload / Re-index\n• Status tracking"]
        Sess["Session Sidebar\n• History / Switch sessions"]
        Cite["Citations Panel\n• Source · Page · Score"]
    end

    subgraph Backend["Backend — FastAPI / Python 3.12 (port 8001)"]
        subgraph Routers["API Routers"]
            ChatR["/chat/stream  SSE\n/chat  JSON"]
            DocR["/documents\nUpload · List · Delete · Reindex"]
            SessR["/sessions\nCRUD · Message history"]
        end

        subgraph AgentLayer["Agent Layer"]
            Orch["AgentOrchestrator\nTool-use loop  max 8 steps\nYields SSE events per step"]
            WMem["Working Memory\nPer-request tool call trace\nRAG chunk accumulator"]
            EMem["Episodic Memory Store\nVectorised past analyses\nStored after each session"]
        end

        subgraph ToolSet["6 Agent Tools"]
            TR["recall_past_analyses\nSearch episodic memory"]
            TS["search_documents\nHybrid RAG + Re-rank"]
            TP["get_stock_price\nOHLCV · period hi/lo · change%"]
            TF["get_fundamentals\nValuation · Growth · Health"]
            TT["technical_analysis\nRSI · MACD · BB · SMA/EMA · ATR"]
            TN["get_stock_news\nyfinance headlines"]
        end

        subgraph Retrieval["Retrieval Pipeline  — Phase 1"]
            BM25["BM25 Sparse Encoder\nFNV-1a hash · BM25-TF\nExact keyword matching"]
            Dense["Dense Embedder\nall-MiniLM-L6-v2  384-dim\nSemantic matching"]
            Hyde["HyDE  optional\nGenerate hypothetical answer\nEmbed answer not question"]
            Hybrid["Qdrant Hybrid Search\nDense + Sparse prefetch\nRRF fusion  20 candidates"]
            Rerank["CrossEncoder Reranker\nms-marco-MiniLM-L-6-v2\nTop 6 of 20 candidates"]
        end

        Ingest["Ingestion Pipeline\nPDF · DOCX · PPTX · HTML · Images\nPyMuPDF · Unstructured\nImage captions via Claude Vision\nRecursive chunking  512c / 128 overlap\nBM25 + Dense embed at index time"]
    end

    subgraph Storage["Storage Layer"]
        PG[("PostgreSQL\nSessions\nMessages\nDocument metadata\nChunk records")]
        QD[("Qdrant\ndocuments collection\n384-dim dense + BM25 sparse\n\nepisodes collection\nPast analysis vectors")]
        MIO[("MinIO  S3-compatible\nRaw document files")]
    end

    subgraph External["External APIs"]
        Claude["Anthropic Claude\nclaude-sonnet-4-6\nTool-use · Streaming\nVision  image captions\nHyDE generation"]
        YF["yfinance\nPrice · Fundamentals\nTechnicals · News\nno API key required"]
    end

    Chat & Docs & Sess --> ChatR & DocR & SessR
    ChatR --> Orch
    DocR --> Ingest
    SessR --> PG
    Orch --> WMem & EMem
    Orch -->|"tool rounds"| Claude
    Orch -->|"final streaming answer"| Claude
    Orch --> TR & TS & TP & TF & TT & TN
    TS --> BM25 & Dense & Hyde
    Hyde -->|"hypothetical answer embedding"| Dense
    BM25 & Dense --> Hybrid
    Hybrid --> Rerank
    TR & EMem --> QD
    TP & TF & TT & TN --> YF
    Ingest -->|"raw files"| MIO
    Ingest -->|"BM25 + dense vectors"| QD
    Ingest -->|"chunk records + metadata"| PG
    Ingest -->|"image captions"| Claude
    ChatR -->|"persist exchange + episodic store"| PG & QD
```

---

## 2. Request Lifecycle — Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI /chat/stream
    participant Orch as AgentOrchestrator
    participant Claude as Claude API
    participant Tools as Agent Tools
    participant QD as Qdrant
    participant PG as PostgreSQL
    participant YF as yfinance

    User->>FE: "Analyse AAPL"
    FE->>API: POST /chat/stream  SSE
    API->>PG: get/create session + load history
    API->>Orch: stream(message, history, session_id, mode)
    Orch-->>FE: event: session

    loop Tool-use loop  max 8 rounds
        Orch->>Claude: messages + tools  non-streaming
        Claude-->>Orch: ToolUseBlock  e.g. recall_past_analyses

        Orch-->>FE: event: tool_call

        alt recall_past_analyses
            Orch->>QD: semantic search  episodes collection
            QD-->>Orch: prior analyses + dates
        else search_documents
            Orch->>QD: hybrid search  dense + BM25 via RRF  20 candidates
            QD-->>Orch: candidate chunks
            Orch->>Orch: CrossEncoder rerank  top 6
        else get_stock_price / get_fundamentals / technical_analysis / get_stock_news
            Orch->>YF: fetch market data
            YF-->>Orch: OHLCV / fundamentals / indicators / headlines
        end

        Orch-->>FE: event: tool_result
        Orch->>Orch: append result to messages
    end

    Orch->>Claude: final messages  streaming  no tools
    loop token stream
        Claude-->>Orch: text delta
        Orch-->>FE: event: delta
    end

    Orch-->>FE: event: done  latency_ms · steps · chunks

    API->>PG: persist user + assistant messages
    API->>QD: store episode  if tickers were analysed
    FE->>User: rendered answer + citations
```

---

## 3. Retrieval Pipeline — Phase 1 Detail

```mermaid
graph LR
    Q["User Query\ne.g. AAPL DCF valuation"]

    subgraph SparseArm["Sparse Branch  keyword matching"]
        BM25E["BM25 Encoder\ntokenise · FNV-1a hash\nBM25-TF weights"]
        SpVec["Sparse Vector\nindices + values\n131072-dim vocabulary"]
    end

    subgraph DenseArm["Dense Branch  semantic matching"]
        direction TB
        Hyde["HyDE  optional\nClaude generates\nhypothetical passage"]
        DenseE["Dense Embedder\nall-MiniLM-L6-v2\n384-dim cosine"]
        DenseVec["Dense Vector\n384 floats"]
    end

    subgraph QdrantHybrid["Qdrant Hybrid Search"]
        PFDense["Prefetch Dense\nlimit 20"]
        PFSparse["Prefetch Sparse\nlimit 20"]
        RRF["Reciprocal Rank Fusion\nmerge + re-score by rank\nfinal 20 candidates"]
    end

    Reranker["CrossEncoder Reranker\nms-marco-MiniLM-L-6-v2\n20 query+passage pairs\nsigmoid-normalised scores"]
    Result["Top 6 Chunks\nhigh-precision citations\nSource · Page · Score"]

    Q --> BM25E --> SpVec --> PFSparse
    Q --> Hyde --> DenseE
    Q --> DenseE --> DenseVec --> PFDense
    PFDense & PFSparse --> RRF --> Reranker --> Result
```

---

## 4. Memory Architecture

```mermaid
graph TB
    subgraph WorkingMem["Working Memory  per-request  in-process"]
        WM1["Tool Call Records\nstep · tool_name · input · result"]
        WM2["RAG Chunk Accumulator\ndeduplicated across tool calls\nexposed as citations on done event"]
    end

    subgraph ConvMem["Conversation Memory  cross-turn  PostgreSQL"]
        CM1["Messages table\nrole · content · retrieved_chunks\nlatency_ms · session_id"]
        CM2["Sessions table\ntitle  auto from first message\ncreated_at · updated_at"]
        CM3["Last 10 messages loaded\nas history on each request"]
    end

    subgraph SemanticMem["Semantic Memory  cross-session  Qdrant documents"]
        SM1["Document Chunks\ndense + BM25 sparse vectors\nsource · page · content_type"]
        SM2["Retrieved via hybrid search\nRRF fusion + CrossEncoder rerank"]
    end

    subgraph EpisodicMem["Episodic Memory  cross-session  Qdrant episodes"]
        EM1["Episode Vectors\nquestion + tickers + answer summary\nembedded with all-MiniLM-L6-v2"]
        EM2["Episode Payload\nsession_id · tickers · tools_used\ntimestamp · full_answer"]
        EM3["Stored after every session\nthat analysed at least one ticker"]
        EM4["Recalled via recall_past_analyses tool\noptional ticker filter\nscore threshold 0.35"]
    end

    Request(("New Request")) --> WorkingMem
    WorkingMem -->|"done event"| ConvMem
    WorkingMem -->|"tickers analysed"| EpisodicMem
    Request --> ConvMem
    Request --> SemanticMem
    Request --> EpisodicMem
```

---

## 5. Component Inventory

| Component | Technology | Purpose |
|---|---|---|
| Frontend | React 18 · TypeScript · Tailwind · Vite | Chat UI, document manager, session history |
| Backend API | FastAPI · Uvicorn · SSE-Starlette | HTTP + streaming SSE endpoints |
| Agent Orchestrator | Custom · Anthropic SDK tool_use | Multi-step planning and tool execution |
| Dense Embedder | sentence-transformers/all-MiniLM-L6-v2 | 384-dim semantic vectors |
| Sparse Embedder | Custom BM25 (no deps) | Keyword / ticker matching |
| Re-ranker | CrossEncoder ms-marco-MiniLM-L-6-v2 | Precision pass over hybrid candidates |
| Vector Store | Qdrant v1.13.6 | Dense + sparse vectors, hybrid RRF search |
| Relational DB | PostgreSQL 15 | Sessions, messages, document metadata |
| Object Storage | MinIO (S3-compatible) | Raw uploaded document files |
| LLM | Claude claude-sonnet-4-6 | Reasoning, tool-use, streaming, vision |
| Market Data | yfinance | Price, fundamentals, technicals, news |
| Ingestion | PyMuPDF · pymupdf4llm · Unstructured | PDF, DOCX, PPTX, HTML, image parsing |
| Chunking | LangChain RecursiveCharacterTextSplitter | 512-char chunks, 128-char overlap |
| Infra | Docker Compose | Fully containerised local deployment |

---

## 6. Feature Flags  `.env`

| Variable | Default | Effect |
|---|---|---|
| `USE_HYBRID_SEARCH` | `true` | Enable BM25 sparse + dense RRF fusion |
| `USE_RERANKING` | `true` | CrossEncoder second-pass over 20 candidates |
| `RERANK_CANDIDATES` | `20` | How many candidates to fetch before re-ranking |
| `USE_HYDE` | `false` | Generate hypothetical answer before dense embed |
| `AGENT_DOMAIN` | `stock_analysis` | System prompt domain: `stock_analysis` or `general` |
| `AGENT_MAX_STEPS` | `8` | Max tool-call rounds per request |
| `CHAT_MODE` | `expert_context` | Default mode: `expert_context` or `strict_rag` |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model for dense vectors |
| `RETRIEVAL_TOP_K` | `8` | Final chunks returned after re-ranking |
