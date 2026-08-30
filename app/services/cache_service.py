"""
Hybrid Response Cache - caches responses with session context awareness.
Provides instant responses for repeated questions.
"""
import hashlib
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.redis import redis_client

logger = logging.getLogger(__name__)

# Cache TTL (5 minutes default)
RESPONSE_CACHE_TTL = 300


async def get_cached_response(session_id: str, query: str) -> Optional[Dict[str, Any]]:
    """Get cached response if available."""
    cache_key = f"resp:{session_id}:{hashlib.md5(query.encode()).hexdigest()}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    return None


async def set_cached_response(session_id: str, query: str, response: Dict[str, Any], ttl: int = RESPONSE_CACHE_TTL):
    """Cache a response with TTL."""
    cache_key = f"resp:{session_id}:{hashlib.md5(query.encode()).hexdigest()}"
    await redis_client.setex(cache_key, ttl, json.dumps(response, default=str))


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    return {
        "status": "success",
        "note": "Redis-based hybrid cache active"
    }
