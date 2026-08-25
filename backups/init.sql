-- =============================================================================
-- AI Ecosystem V2.0 - Inicjalizacja struktur bazy danych (Postgres + pgvector)
-- Lokalizacja: /backup/schema.sql
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Pamięć agenta (L1) - wpis z embeddings vectorów (wymiar 1024 z mxbai-embed-large)
CREATE TABLE IF NOT EXISTS agent_memory (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1024),
    metadata JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Historia okna kontekstu (L3) - ostatnie Q&A
CREATE TABLE IF NOT EXISTS rag_history (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    question TEXT,
    answer TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Nowoczesny indeks HNSW dla szybkiego wyszukiwania semantycznego
CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx
    ON agent_memory USING hnsw (embedding vector_cosine_ops);