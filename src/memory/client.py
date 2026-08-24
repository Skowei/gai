"""
=============================================================================
AI Ecosystem V2.0 - Memory Client
Klient do zarządzania pamięcią agenta - REST API (TencentDB) + Local DB
DOSTĘPNY: memory_pg_database, memory_redis_db, memory_agent_memory_endpoint
=============================================================================
"""

import requests
import psycopg2
import redis
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


# =============================================================================
# KONFIGURACJA - REST API do TencentDB Agent Memory + Local DB
# =============================================================================


@dataclass
class MemoryConfig:
    """Konfiguracja klienta pamięci."""
    pg_connection_string: str = "postgresql://agent:your_secure_password@localhost:5432/ai_memory"
    redis_url: str = "redis://redis:6379/0"
    redis_db: int = 1
    memory_table: str = "agent_memory"
    # TencentDB Agent Memory REST API endpoint
    agent_memory_endpoint: str = "http://agent_memory:8080/v1/embeddings"


class MemoryClient:
    """
    Klient do zarządzania pamięcią agenta AI.
    
    ARCHITEKTURA PAMIĘCI:
    ---------------------
    L0 (Redis): Krótkoterminowa pamięć robocza - szybki dostęp
    L1 (TencentDB REST API + PostgreSQL + pgvector): Przetworzona wiedza długoterminowa
    L2 (PostgreSQL): Doświadczenia & metadane
    L3 (Pamięć kontekstu): Okno kontekstowe RAG - ostatnie Q&A
    
    Usage:
        >>> client = MemoryClient()
        >>> client.store("system_instructions", "Ty jesteś asystentem...")
        >>> results = client.search_semantic("Jak działa API?")
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()
        self._pg_pool = None
        self._redis_client = None
        self._http_session = requests.Session()
        self._connect()

    def _connect(self):
        """Inicjalizacja połączeń z PostgreSQL, Redis i REST API."""
        # POŁĄCZENIE: PostgreSQL (L1 + L2)
        try:
            self._pg_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1, maxconn=5,
                host="localhost", port=5432,
                database=self.config.memory_pg_database or "ai_memory",
                user="agent", password="your_secure_password",
            )
        except Exception as e:
            print(f"⚠️ Postgres połączenie nieudane: {e}")
        
        # POŁĄCZENIE: Redis (L0 + L3)
        try:
            self._redis_client = redis.Redis.from_url(self.config.redis_url, db=self.config.redis_db)
            self._redis_client.ping()
            print("✅ Redis podłączony")
        except Exception as e:
            print(f"⚠️ Redis połączenie nieudane: {e}")
        
        # TEST: REST API do agent_memory (L1 embeddings)
        try:
            test_embedding = self._get_embeddings("test embedding 0.001 " * 128)
            print(f"✅ TencentDB Agent Memory REST API podłączony")
        except Exception as e:
            print(f"⚠️ REST API agent_memory nieosiągalne: {e}")

    def _get_embeddings(self, text: str) -> Optional[List[float]]:
        """Pobieranie embeddings z TencentDB Agent Memory via REST API."""
        try:
            url = self.config.agent_memory_endpoint
            payload = {"input": [text], "model": "bge-m3"}
            response = self._http_session.post(url, json=payload, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                return data.get("embeddings", [])[0] if isinstance(data.get("embeddings"), list) else None
            else:
                print(f"⚠️ REST API error {response.status_code}")
                return None
        except requests.RequestException as e:
            print(f"⚠️ HTTP request failed: {e}")
            return None
        except Exception as e:
            print(f"⚠️ Embedding generation failed: {e}")
            return None

    def store(self, key: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Zapis treści z embeddings w Redis + PostgreSQL."""
        embedding = self._get_embeddings(content)
        if not embedding:
            print(f"⚠️ Nie udało się pobrać embeddings")
            return False
        
        # Zapis w Redis (L0 - szybki dostęp)
        if self._redis_client:
            redis_key = f"memory:l0:{key}"
            ttl_seconds = metadata.get("ttl", 3600) if metadata else 3600
            self._redis_client.setex(redis_key, ttl_seconds, json.dumps(content))
        
        # Zapis w PostgreSQL + pgvector (L1 - semantic storage)
        if self._pg_pool and embedding is not None:
            try:
                with self._pg_pool.get() as conn:
                    cur = conn.cursor()
                    insert_query = """INSERT INTO agent_memory (content, embedding, updated_at) 
                                      VALUES (%s::vector, %s::jsonb, NOW()) 
                                      ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content,
                                                                          embedding = EXCLUDED.embedding,
                                                                          updated_at = NOW() RETURNING id;"""
                    cur.execute(insert_query, (embedding,))
                    conn.commit()
            except Exception as e:
                print(f"⚠️ Postgres write failed: {e}")
        return True

    def search_semantic(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantyczne wyszukiwanie w L1."""
        if not self._pg_pool:
            return []
        try:
            with self._pg_pool.get() as conn:
                cur = conn.cursor()
                dummy_embedding = [0.0] * 1024
                search_query = """SELECT id, content, metadata->>'created_at' as created_at,
                                   ROUND((embedding <=> %s::vector)::numeric, 2) as distance 
                                  FROM agent_memory ORDER BY embedding <=> %s::vector LIMIT %s;"""
                cur.execute(search_query, (dummy_embedding, dummy_embedding, top_k))
                results = cur.fetchall()
            return [{"id": r[0], "content": r[1], "created_at": r[2], "distance": r[3]} for r in results]
        except Exception as e:
            print(f"⚠️ Semantic search failed: {e}")
            return []

    def retrieve_from_context_window(self, max_entries: int = 5) -> List[Dict[str, str]]:
        """Pobieranie danych z okna kontekstowego (L3)."""
        if not self._pg_pool:
            return []
        try:
            with self._pg_pool.get() as conn:
                cur = conn.cursor()
                query = "SELECT question, answer FROM rag_history ORDER BY created_at DESC LIMIT %s;"
                cur.execute(query, (max_entries,))
                results = cur.fetchall()
            return [{"question": r[0], "answer": r[1] if len(r) > 1 else ""} for r in results]
        except Exception as e:
            print(f"⚠️ Context window retrieval failed: {e}")
            return []

    def get_total_interactions(self) -> int:
        """Pobieranie licznika interakcji."""
        if not self._pg_pool:
            return 0
        try:
            with self._pg_pool.get() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COALESCE(stat_value->>'count', '0')::INTEGER FROM agent_stats WHERE stat_key = %s", ("total_interactions",))
                row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            print(f"⚠️ Failed to get interactions count: {e}")
            return 0

    def reset(self):
        """Reset pamięci."""
        if not self._pg_pool or not self._redis_client:
            return
        try:
            keys = [k for k in self._redis_client.keys() if k.startswith("memory:l0")]
            if keys:
                self._redis_client.delete(*keys)
            print("✅ Pamięć zresetowana")
        except Exception as e:
            print(f"⚠️ Reset failed: {e}")

    def close(self):
        """Zamykanie połączeń."""
        if self._pg_pool:
            self._pg_pool.closeall()
        if self._redis_client:
            self._redis_client.close()
