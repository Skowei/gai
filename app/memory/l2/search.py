"""
L2: Memory Search - Semantic and Hybrid search
"""
import asyncio
import json
import logging
from typing import List, Dict, Any
from app.services.llm_service import LLMFactory
from app.memory.l2.client import format_embedding_for_pgvector

logger = logging.getLogger(__name__)


class MemorySearch:
    """
    L2: Search operations for memory retrieval.
    Supports semantic, keyword, and hybrid search.
    """
    
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
    
    async def semantic_search(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Pure semantic search using embeddings."""
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()
        
        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(None, embed_engine.embed_query, query_text)
        query_embedding_str = format_embedding_for_pgvector(query_embedding)

        async with self.memory_manager.pool.acquire() as conn:
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

    async def keyword_search(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Pure keyword search using full-text search."""
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()
        
        async with self.memory_manager.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT file_path, content, metadata, 
                       ts_rank(content_tsv, plainto_tsquery('english', $1)) as rank
                FROM agent_memory
                WHERE content_tsv @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $2;
                """,
                query_text, limit
            )
            return [
                {
                    "file_path": r["file_path"],
                    "content": r["content"],
                    "metadata": json.loads(r["metadata"]),
                    "rank": round(float(r["rank"]), 4)
                } for r in rows
            ]

    async def hybrid_search(self, query_text: str, limit: int = 5,
                            semantic_weight: float = 0.7, keyword_weight: float = 0.3) -> List[Dict[str, Any]]:
        """
        Hybrid search combining semantic and keyword results.
        Uses reciprocal rank fusion for combining scores.
        """
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()
        
        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(None, embed_engine.embed_query, query_text)
        query_embedding_str = format_embedding_for_pgvector(query_embedding)

        async with self.memory_manager.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH semantic_results AS (
                    SELECT file_path, content, metadata,
                           1.0 / (1.0 + (embedding <=> $1)) as semantic_score
                    FROM agent_memory
                    ORDER BY embedding <=> $1
                    LIMIT $2 * 3
                ),
                keyword_results AS (
                    SELECT file_path, content, metadata,
                           ts_rank(content_tsv, plainto_tsquery('english', $3)) as keyword_score
                    FROM agent_memory
                    WHERE content_tsv @@ plainto_tsquery('english', $3)
                    ORDER BY ts_rank(content_tsv, plainto_tsquery('english', $3)) DESC
                    LIMIT $2 * 3
                ),
                combined AS (
                    SELECT 
                        COALESCE(s.file_path, k.file_path) as file_path,
                        COALESCE(s.content, k.content) as content,
                        COALESCE(s.metadata, k.metadata) as metadata,
                        COALESCE(s.semantic_score, 0) * $4 as weighted_semantic,
                        COALESCE(k.keyword_score, 0) * $5 as weighted_keyword
                    FROM semantic_results s
                    FULL OUTER JOIN keyword_results k ON s.file_path = k.file_path
                )
                SELECT file_path, content, metadata, 
                       (weighted_semantic + weighted_keyword) as combined_score
                FROM combined
                ORDER BY combined_score DESC
                LIMIT $2;
                """,
                query_embedding_str, limit, query_text, semantic_weight, keyword_weight
            )
            
            results = []
            for r in rows:
                try:
                    metadata = json.loads(r["metadata"])
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
                results.append({
                    "file_path": r["file_path"],
                    "content": r["content"],
                    "metadata": metadata,
                    "score": round(float(r["combined_score"]), 4)
                })
            
            return results
