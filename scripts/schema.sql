-- Infigo Bot — minimal Neon schema (RAG + public chat only)
-- psql "$DATABASE_URL" -f scripts/schema.sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_articles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    body TEXT NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'faq'
);

ALTER TABLE kb_articles ADD COLUMN IF NOT EXISTS search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))) STORED;
CREATE INDEX IF NOT EXISTS idx_kb_search_vector ON kb_articles USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS rag_documents (
    id SERIAL PRIMARY KEY,
    owner_user_id INTEGER,
    title VARCHAR(300) NOT NULL,
    body TEXT NOT NULL,
    source_type VARCHAR(32) NOT NULL CHECK (source_type IN ('text', 'file', 'api', 'feed', 'learned', 'webhook')),
    source_ref VARCHAR(500),
    category VARCHAR(64) NOT NULL DEFAULT 'infigo',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_created ON rag_documents (created_at DESC);

ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))) STORED;
CREATE INDEX IF NOT EXISTS idx_rag_search_vector ON rag_documents USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id SERIAL PRIMARY KEY,
    source_table VARCHAR(32) NOT NULL CHECK (source_table IN ('kb_articles', 'rag_documents')),
    source_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    title_hint VARCHAR(300) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_table, source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source ON knowledge_chunks (source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER,
    erp_uid VARCHAR(64) NOT NULL,
    channel VARCHAR(32) NOT NULL DEFAULT 'site',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions (updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    llm_source VARCHAR(32),
    confidence REAL,
    intent_class VARCHAR(64),
    sources_used INTEGER DEFAULT 0,
    rag_document_id INTEGER REFERENCES rag_documents (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id, created_at);

COMMIT;
