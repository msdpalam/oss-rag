"""
Application configuration via pydantic-settings.
All values can be overridden with environment variables.
"""

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    # Stored as a comma-separated string so pydantic-settings v2 doesn't try
    # to JSON-parse it; use the cors_origins property wherever a list is needed.
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── Claude ────────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 2048
    CLAUDE_TEMPERATURE: float = 0.0

    # ── Embeddings ────────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DIMENSIONS: int = 384

    # ── Qdrant ────────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "documents"

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb"

    # ── MinIO / S3 ────────────────────────────────────────────────────────────
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "ragapp"
    S3_SECRET_KEY: str = "ragapp123"
    S3_BUCKET_DOCUMENTS: str = "documents"
    S3_BUCKET_PROCESSED: str = "documents-processed"
    S3_REGION: str = "us-east-1"

    # ── RAG tuning ────────────────────────────────────────────────────────────
    RETRIEVAL_TOP_K: int = 8
    RETRIEVAL_SCORE_THRESHOLD: float = 0.3
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 128

    # Hybrid search: dense (semantic) + sparse (BM25 keyword) fused via RRF
    USE_HYBRID_SEARCH: bool = True

    # Re-ranking: CrossEncoder second-pass over RERANK_CANDIDATES, returns top RETRIEVAL_TOP_K
    USE_RERANKING: bool = True
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANK_CANDIDATES: int = 20  # how many to fetch from Qdrant before reranking

    # HyDE: generate a hypothetical answer, embed it, use that for dense retrieval
    # Adds ~1 Claude API call per search — off by default, enable when latency is acceptable
    USE_HYDE: bool = False
    HYDE_MAX_TOKENS: int = 200

    # ── Chat mode ─────────────────────────────────────────────────────────────
    # "strict_rag"      — answer only from indexed documents
    # "expert_context"  — full LLM knowledge + documents as grounding context
    CHAT_MODE: str = "expert_context"

    # ── Agent settings ────────────────────────────────────────────────────────
    # Domain controls which system prompt and tool set the agent uses.
    # Switch domain here without changing any other code.
    AGENT_DOMAIN: str = "stock_analysis"  # stock_analysis | general
    AGENT_MAX_STEPS: int = 8  # max tool-call rounds before forcing final answer


settings = Settings()
