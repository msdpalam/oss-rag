-- ─────────────────────────────────────────────────────────────────────────────
-- OSS RAG Stack — PostgreSQL Schema
-- Runs automatically on first container start
-- ─────────────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Users ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    display_name  VARCHAR(255),
    email         VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Investor Profiles ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS investor_profiles (
    user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    age                      INTEGER CHECK (age BETWEEN 18 AND 100),
    risk_tolerance           INTEGER CHECK (risk_tolerance BETWEEN 1 AND 5),
    horizon_years            INTEGER CHECK (horizon_years BETWEEN 1 AND 50),
    goals                    TEXT[],
    portfolio_size_usd       BIGINT,
    monthly_contribution_usd INTEGER,
    tax_accounts             TEXT[],
    preferred_agent          VARCHAR(50),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_investor_profiles_user ON investor_profiles(user_id);

-- ── Sessions ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    message_count   INTEGER NOT NULL DEFAULT 0,
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

-- ── Chat History ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retrieved_chunks    JSONB,
    search_query        TEXT,
    model_used          VARCHAR(100),
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    latency_ms          INTEGER,
    feedback            VARCHAR(10) CHECK (feedback IN ('up', 'down')),
    feedback_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);

-- ── Document Registry ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename        VARCHAR(500) NOT NULL,
    original_name   VARCHAR(500) NOT NULL,
    content_type    VARCHAR(100),
    size_bytes      BIGINT,
    s3_key          VARCHAR(1000) NOT NULL,
    s3_bucket       VARCHAR(255) NOT NULL,
    status          VARCHAR(50) NOT NULL DEFAULT 'uploaded'
                    CHECK (status IN ('uploaded', 'processing', 'indexed', 'failed')),
    error_message   TEXT,
    page_count      INTEGER,
    chunk_count     INTEGER,
    has_images      BOOLEAN DEFAULT FALSE,
    uploaded_by     UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    indexed_at      TIMESTAMPTZ,
    title           VARCHAR(500),
    author          VARCHAR(255),
    doc_language    VARCHAR(10),
    tags            TEXT[]
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm ON documents USING gin(title gin_trgm_ops);

-- ── Document Chunks ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    qdrant_point_id UUID NOT NULL,
    chunk_index     INTEGER NOT NULL,
    page_number     INTEGER,
    content         TEXT NOT NULL,
    content_type    VARCHAR(20) DEFAULT 'text'
                    CHECK (content_type IN ('text', 'table', 'image_caption')),
    char_count      INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_qdrant_id ON document_chunks(qdrant_point_id);

-- ── Virtual Portfolio ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS portfolio_positions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker          VARCHAR(20) NOT NULL,
    asset_type      VARCHAR(20) NOT NULL DEFAULT 'stock'
                    CHECK (asset_type IN ('stock', 'etf', 'crypto', 'crypto_etf')),
    shares          NUMERIC(18, 6) NOT NULL CHECK (shares > 0),
    avg_cost_usd    NUMERIC(18, 4) NOT NULL CHECK (avg_cost_usd >= 0),
    notes           TEXT,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio_positions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_user_ticker ON portfolio_positions(user_id, ticker);

-- ── Auto-update updated_at triggers ──────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Auto-update session metadata when messages are inserted ───────────────────

CREATE OR REPLACE FUNCTION update_session_on_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE sessions
    SET
        last_message_at = NEW.created_at,
        message_count   = message_count + 1,
        updated_at      = NOW()
    WHERE id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_message_updates_session
    AFTER INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION update_session_on_message();
