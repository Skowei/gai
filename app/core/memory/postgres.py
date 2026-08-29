import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import asyncpg
import aiofiles
from app.core.config import settings
from app.core.llm_factory import LLMFactory

logger = logging.getLogger(__name__)


def format_embedding_for_pgvector(embedding: List[float]) -> str:
    """
    Formats embedding list for pgvector compatibility.
    pgvector expects format: [0.1,0.2,0.3] (no spaces after commas)
    """
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"


class UnifiedMemoryManager:
    """
    Zintegrowany, asynchroniczny menedżer pamięci hybrydowej Enterprise (L0-L4).
    L2 (Semantyka) -> Postgres + pgvector + JSONB
    L3 (Operacyjna) -> Internal Agent Cache (/app/local_notes)
    L4 (Globalna) -> Obsidian Vault (/app/obsidian_vault - Read Only)
    """
    def __init__(self):
        self.vault_path = Path("/app/obsidian_vault")
        self.local_notes_path = Path("/app/local_notes")
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Inicjalizacja puli połączeń oraz automatyczna auto-migracja struktur (Self-Healing)"""
        if not self.pool:
            logger.info("[Pamięć] Nawiązuję asynchroniczne połączenie z PostgreSQL...")
            self.pool = await asyncpg.create_pool(settings.database_url)

            async with self.pool.acquire() as conn:
                logger.info("[Pamięć] Sprawdzam i migruję strukturę bazy danych...")
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS agent_memory (
                        id SERIAL PRIMARY KEY,
                        file_path TEXT UNIQUE,
                        content TEXT NOT NULL,
                        embedding vector(1024),
                        metadata JSONB NOT NULL DEFAULT '{}',
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

                try:
                    await conn.execute("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint
                                WHERE conname = 'agent_memory_file_path_key'
                            ) THEN
                                ALTER TABLE agent_memory ADD CONSTRAINT agent_memory_file_path_key UNIQUE (file_path);
                            END IF;
                        END $$;
                    """)
                except Exception as sql_err:
                    logger.warning(f"[Pamięć Migracja] Info UNIQUE: {sql_err}")

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS rag_history (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        question TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx
                    ON agent_memory USING hnsw (embedding vector_cosine_ops);
                """)

            self.local_notes_path.mkdir(parents=True, exist_ok=True)
            for folder in ["knowledge_base", "code_snippets", "robotics", "system_logs"]:
                (self.local_notes_path / folder).mkdir(parents=True, exist_ok=True)

    async def save_to_vault_and_vector(self, rel_path: str, content: str, metadata: Dict[str, Any]):
        """[POZIOM L4] Zapisuje do Obsidiana (vault) i synchronizuje z Postgresem."""
        if not self.pool:
            await self.initialize()

        full_path = self.vault_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, mode='w', encoding='utf-8') as f:
            await f.write(content)

        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, embed_engine.embed_query, content)
        embedding_str = format_embedding_for_pgvector(embedding)

        metadata["memory_level"] = "L4"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_memory (file_path, content, embedding, metadata, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (file_path)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW();
                """,
                f"obsidian_vault/{rel_path}", content, embedding_str, json.dumps(metadata)
            )
        logger.info(f"📌 [Pamięć L4 + L2] Zsynchronizowano notatkę Obsidiana: {rel_path}")

    async def save_to_local_notes_and_vector(self, rel_path: str, content: str, metadata: Dict[str, Any]):
        """
        [PRODUKCYJNY POZIOM L3]
        Zapisuje wewnętrzne przemyślenia i fakty Agenta w dedykowanym folderze operacyjnym (L3),
        całkowicie omijając i chroniąc prywatny Obsidian użytkownika (L4).
        Następnie generuje embedding i robi UPSERT do Postgresa (L2).
        """
        if not self.pool:
            await self.initialize()

        full_path = self.local_notes_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        frontmatter = f"---\nengine: DeepSeek-R1-8B\nsession_id: {metadata.get('session_id', 'unknown')}\n---\n"
        file_content = f"{frontmatter}\n# Log operacyjny Agenta\n\n{content}"

        async with aiofiles.open(full_path, mode='w', encoding='utf-8') as f:
            await f.write(file_content)

        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, embed_engine.embed_query, content)
        embedding_str = format_embedding_for_pgvector(embedding)

        metadata["memory_level"] = "L3"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_memory (file_path, content, embedding, metadata, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (file_path)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW();
                """,
                f"internal_cache/{rel_path}", content, embedding_str, json.dumps(metadata)
            )
        logger.info(f"📌 [Pamięć L3 + L2] Zsynchronizowano wewnętrzny brudnopis operacyjny: {rel_path}")

    async def log_chat_interaction(self, session_id: str, question: str, answer: str):
        if not self.pool:
            await self.initialize()
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO rag_history (session_id, question, answer) VALUES ($1, $2, $3);",
                session_id, question, answer
            )

    async def semantic_search(self, query_text: str, limit: int = 3) -> List[Dict[str, Any]]:
        if not self.pool:
            await self.initialize()
        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(None, embed_engine.embed_query, query_text)
        query_embedding_str = format_embedding_for_pgvector(query_embedding)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT file_path, content, metadata, (embedding <=> $1) as distance
                FROM agent_memory
                ORDER BY distance ASC
                LIMIT $2;
                """,
                query_embedding_str, limit
            )
            return [
                {
                    "file_path": r["file_path"],
                    "content": r["content"],
                    "metadata": json.loads(r["metadata"]),
                    "similarity": round(1 - r["distance"], 4)
                } for r in rows
            ]

    async def close(self):
        if self.pool:
            await self.pool.close()
