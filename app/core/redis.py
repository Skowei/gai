"""
Shared Redis client - single source of truth for Redis connection.
Eliminates circular imports between modules.
"""
import hashlib
import asyncio
import redis.asyncio as aioredis
from app.core.config import settings

# Single shared Redis client
redis_client = aioredis.from_url(
    settings.redis_url,
    decode_responses=True
)

# Embedding cache TTL (24 hours)
EMBEDDING_CACHE_TTL = 86400


async def get_cached_embedding(embed_engine, query: str) -> str:
    """
    Returns cached embedding or generates and caches new one.
    """
    cache_key = f"emb:{hashlib.md5(query.encode()).hexdigest()}"
    
    # Try cache first
    cached = await redis_client.get(cache_key)
    if cached:
        return cached
    
    # Generate embedding
    loop = asyncio.get_running_loop()
    embedding = await loop.run_in_executor(None, embed_engine.embed_query, query)
    
    # Import here to avoid circular import at module level
    from app.memory.l2.client import format_embedding_for_pgvector
    embedding_str = format_embedding_for_pgvector(embedding)
    
    # Cache for future use
    await redis_client.setex(cache_key, EMBEDDING_CACHE_TTL, embedding_str)
    
    return embedding_str
