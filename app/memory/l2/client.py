"""
L2: PostgreSQL Client - Connection and migrations
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional
import asyncpg
from app.core.config import settings

logger = logging.getLogger(__name__)


def format_embedding_for_pgvector(embedding: List[float]) -> str:
    """
    Formats embedding list for pgvector compatibility.
    pgvector expects format: [0.1,0.2,0.3] (no spaces after commas)
    """
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"


class UnifiedMemoryManager:
    """
    L2: Semantic Memory Manager
    PostgreSQL + pgvector for document storage and retrieval.
    """
    def __init__(self):
        self.vault_path = Path("/app/obsidian_vault")
        self.local_notes_path = Path("/app/local_notes")
        self.pool: Optional[asyncpg.Pool] = None
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize connection pool and run migrations (idempotent, concurrency-safe)."""
        async with self._init_lock:
            if not self.pool:
                logger.info("[L2] Connecting to PostgreSQL...")
                self.pool = await asyncpg.create_pool(settings.database_url)
                await self._run_migrations()

    async def _run_migrations(self):
        """Run database migrations."""
        async with self.pool.acquire() as conn:
            logger.info("[L2] Running migrations...")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Main memory table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id SERIAL PRIMARY KEY,
                    file_path TEXT UNIQUE,
                    content TEXT NOT NULL,
                    embedding vector(1024),
                    metadata JSONB NOT NULL DEFAULT '{}',
                    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # Conversation history table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_history (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # Indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx
                ON agent_memory USING hnsw (embedding vector_cosine_ops);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS agent_memory_tsv_idx
                ON agent_memory USING GIN (content_tsv);
            """)

        # Ensure local directories exist
        self.local_notes_path.mkdir(parents=True, exist_ok=True)
        for folder in ["knowledge_base", "code_snippets", "robotics", "system_logs"]:
            (self.local_notes_path / folder).mkdir(parents=True, exist_ok=True)

    async def log_chat_interaction(self, session_id: str, question: str, answer: str):
        """
        Archive a chat interaction to the L2 rag_history table.
        Graceful degradation: if the pool is not initialized, skip instead of raising.
        """
        if not self.pool:
            logger.info("[L2] Pool not initialized - lazy self-healing init")
            await self.initialize()
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO rag_history (session_id, question, answer)
                    VALUES ($1, $2, $3)
                    """,
                    session_id, question, answer
                )
            logger.info(f"[L2] Archived chat interaction for session '{session_id}'")
        except Exception as e:
            logger.error(f"[L2] Failed to archive chat interaction: {e}")
            raise

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
