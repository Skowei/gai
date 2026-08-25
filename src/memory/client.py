"""
==============================================================================
AI Ecosystem V2.0 - Memory Client
L0 (Redis)      - krótkoterminowa pamięć robocza / cache
L1 (PostgreSQL) - pamięć długoterminowa z embeddings (pgvector)
L2/L3 (Postgres)- kontekst okna (ostatnie Q&A)
==============================================================================
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
import redis

log = logging.getLogger("memory")


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


class MemoryConfig:
    """Konfiguracja klienta pamięci (czytana z env)."""

    def __init__(self, pg_connection_string: Optional[str] = None,
                 redis_url: Optional[str] = None,
                 redis_db: int = 0):
        self.pg_connection_string = pg_connection_string or (
            f"postgresql://{_env('MEMORY_PG_USER', 'agent')}:"
            f"{_env('MEMORY_PG_PASSWORD', '12345678')}@"
            f"{_env('MEMORY_PG_HOST', 'postgres')}:"
            f"{_env('MEMORY_PG_PORT', '5432')}/"
            f"{_env('MEMORY_PG_DATABASE', 'ai_memory')}"
        )
        self.redis_url = redis_url or _env("REDIS_URL", "redis://localhost:6379/0")
        self.redis_db = redis_db
        self.memory_table = "agent_memory"
        self.history_table = "rag_history"


class MemoryClient:
    """Klient pamięci agenta AI (README: L0-L3)."""

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()
        self._pg_pool = None
        self._redis = None
        self._connect()

    # ------------------------------------------------------------ połączenia
    def _connect(self) -> None:
        try:
            self._pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1, maxconn=5, dsn=self.config.pg_connection_string
            )
            log.debug("PostgreSQL połączony")
        except Exception as exc:
            log.warning("Postgres połączenie nieudane: %s", exc)

        try:
            self._redis = redis.Redis.from_url(
                self.config.redis_url, db=self.config.redis_db,
                decode_responses=True,
            )
            self._redis.ping()
            log.debug("Redis podłączony")
        except Exception as exc:
            log.warning("Redis połączenie nieudane: %s", exc)

    def _get_embeddings(self, text: str) -> Optional[List[float]]:
        """Embeddings przez lokalną Ollamę (bge-m3)."""
        try:
            from src.llm import ollama_embeddings
            return ollama_embeddings(text)
        except Exception as exc:
            log.debug("Embeddings unavailable: %s", exc)
            return None

    def _ensure_schema(self) -> None:
        """Utworzenie tabeli agent_memory (pgvector) jeśli nie istnieje."""
        if not self._pg_pool:
            return
        try:
            with self._pg_pool.getconn() as conn:
                try:
                    cur = conn.cursor()
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS {t} (
                            id TEXT PRIMARY KEY,
                            content TEXT NOT NULL,
                            embedding vector(1024),
                            metadata JSONB NOT NULL DEFAULT '{{}}',
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        );
                        """.format(t=self.config.memory_table)
                    )
                    conn.commit()
                finally:
                    self._pg_pool.putconn(conn)
        except Exception as exc:
            log.warning("Schema ensure failed: %s", exc)

    # ------------------------------------------------------------------ zapis
    def store(self, key: str, content: str,
              metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Zapis treści w L0 (Redis) i L1 (Postgres + pgvector)."""
        metadata = metadata or {}
        embedding = self._get_embeddings(content)

        # L0: Redis (krótkoterminowa, TTL)
        if self._redis:
            try:
                ttl = int(metadata.get("ttl", 3600))
                self._redis.setex(f"memory:l0:{key}", ttl, json.dumps(content))
            except Exception as exc:
                log.debug("Redis store failed: %s", exc)

        # L1: Postgres + pgvector
        if self._pg_pool and embedding:
            try:
                self._ensure_schema()
                with self._pg_pool.getconn() as conn:
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO {t} (id, content, embedding, metadata) "
                            "VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (id) DO UPDATE SET "
                            "content = EXCLUDED.content, "
                            "embedding = EXCLUDED.embedding, "
                            "metadata = EXCLUDED.metadata, "
                            "updated_at = NOW();".format(t=self.config.memory_table),
                            (key, content,
                             json.dumps(embedding),
                             json.dumps(metadata, ensure_ascii=False)),
                        )
                        conn.commit()
                    finally:
                        self._pg_pool.putconn(conn)
                return True
            except Exception as exc:
                log.warning("Postgres store failed: %s", exc)
        return bool(self._redis)

    # --------------------------------------------------------------- odczyt
    def single_store(self, key: str) -> Optional[str]:
        """Odczyt jednego wpisu z Redis (L0)."""
        if not self._redis:
            return None
        try:
            raw = self._redis.get(f"memory:l0:{key}")
            if raw:
                return raw
        except Exception:
            pass
        return None

    def search_semantic(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantyczne wyszukiwanie w L1 (pgvector)."""
        if not self._pg_pool:
            return []
        embedding = self._get_embeddings(query)
        if not embedding:
            return []
        try:
            with self._pg_pool.getconn() as conn:
                try:
                    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cur.execute(
                        "SELECT id, content, metadata, "
                        "ROUND((embedding <=> %s::vector)::numeric, 3) AS distance "
                        "FROM {t} ORDER BY embedding <=> %s::vector LIMIT %s;"
                        .format(t=self.config.memory_table),
                        (json.dumps(embedding), json.dumps(embedding), top_k),
                    )
                    rows = cur.fetchall()
                finally:
                    self._pg_pool.putconn(conn)
            return [
                {"id": r["id"], "content": r["content"],
                 "metadata": r["metadata"], "distance": r["distance"]}
                for r in rows
            ]
        except Exception as exc:
            log.debug("Semantic search failed: %s", exc)
            return []

    def retrieve_from_context_window(self, max_entries: int = 5) -> List[Dict[str, str]]:
        """Pobieranie L3: ostatnie Q&A z tabeli history."""
        if not self._pg_pool:
            return []
        try:
            with self._pg_pool.getconn() as conn:
                try:
                    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cur.execute(
                        "SELECT question, answer FROM {t} "
                        "ORDER BY created_at DESC LIMIT %s;"
                        .format(t=self.config.history_table),
                        (max_entries,),
                    )
                    rows = cur.fetchall()
                finally:
                    self._pg_pool.putconn(conn)
            return [{"question": r["question"], "answer": r["answer"]} for r in rows]
        except Exception as exc:
            log.debug("Context window failed: %s", exc)
            return []

    def build_context(self, query: str, top_k: int = 3) -> str:
        """Buduj kontekst RAG (pamięć semantyczna + ostatnie Q&A)."""
        parts = []
        for r in self.search_semantic(query, top_k=top_k)[:top_k]:
            parts.append(f"- {r['content'][:300]}")
        for item in self.retrieve_from_context_window(max_entries=3):
            parts.append(f"- Q: {item['question'][:120]}\n  A: {item['answer'][:200]}")
        return "\n".join(parts)

    def get_total_interactions(self) -> int:
        """Licznik interakcji (z Redis)."""
        if not self._redis:
            return 0
        try:
            return int(self._redis.get("memory:l3:total_interactions") or "0")
        except Exception:
            return 0

    def reset(self) -> None:
        """Reset pamięci L0 (Redis klucze memory:l0:*)."""
        if not self._redis:
            return
        try:
            keys = [k for k in self._redis.keys("memory:l0:*")]
            if keys:
                self._redis.delete(*keys)
            log.info("Pamięć L0 zresetowana (%s kluczy)", len(keys))
        except Exception as exc:
            log.debug("Reset failed: %s", exc)

    def close(self) -> None:
        if self._pg_pool:
            self._pg_pool.closeall()
        if self._redis:
            self._redis.close()


# =============================================================================
# SINGLETON
# =============================================================================

_singleton: Optional[MemoryClient] = None


def get_memory_client(config: Optional[MemoryConfig] = None) -> MemoryClient:
    """Zwraca singleton MemoryClient (bez kolejnych połączeń)."""
    global _singleton
    if _singleton is None:
        _singleton = MemoryClient(config)
    return _singleton
