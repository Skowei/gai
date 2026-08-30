"""
Shared dependencies module - imports from core/redis to avoid circular imports.
"""
from app.core.redis import redis_client, EMBEDDING_CACHE_TTL, get_cached_embedding
from app.memory.l2.client import UnifiedMemoryManager, format_embedding_for_pgvector

# Single shared instance - imported by all nodes
memory_manager = UnifiedMemoryManager()

__all__ = [
    "redis_client",
    "EMBEDDING_CACHE_TTL", 
    "get_cached_embedding",
    "memory_manager",
    "format_embedding_for_pgvector"
]
