import json
import logging
from typing import Dict, Any
import asyncio
import redis.asyncio as aioredis
from app.core.agent.state import AgentState
from app.core.agent.nodes.utils import get_last_user_message, safe_get_attr
from app.memory.l2.client import UnifiedMemoryManager
from app.services.llm_service import LLMFactory
from app.api.deps import get_cached_embedding
from app.core.config import settings

logger = logging.getLogger(__name__)

memory_manager = UnifiedMemoryManager()
redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)


async def fetch_memory_node(state: AgentState) -> Dict[str, Any]:
    """L0-L4: Fetch memory from all layers."""
    user_query = get_last_user_message(state)
    session_id = safe_get_attr(state, "session_id", "default_session")
    redis_key = f"chat_session:{session_id}"
    
    async def get_chat_history():
        try:
            history_json = await redis_client.get(redis_key)
            if history_json:
                messages_list = json.loads(history_json)
                return "\n".join([f"{m['role']}: {m['content']}" for m in messages_list])
        except Exception as e:
            logger.warning(f"[L0 Cache] Redis error: {e}")
        return ""
    
    async def get_postgres_history():
        try:
            if not memory_manager.pool:
                await memory_manager.initialize()
            async with memory_manager.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT question, answer FROM rag_history WHERE session_id = $1 ORDER BY created_at ASC LIMIT 10;",
                    session_id
                )
                if rows:
                    redis_payload = []
                    for r in rows:
                        redis_payload.extend([
                            {"role": "User", "content": r['question']},
                            {"role": "Assistant", "content": r['answer']}
                        ])
                    await redis_client.setex(redis_key, 7200, json.dumps(redis_payload))
                    return "\n".join([f"{m['role']}: {m['content']}" for m in redis_payload])
        except Exception as e:
            logger.warning(f"[L2 History] Postgres error: {e}")
        return ""
    
    chat_history_task = asyncio.create_task(get_chat_history())
    postgres_history_task = asyncio.create_task(get_postgres_history())
    
    chat_history_str = await chat_history_task
    postgres_history = await postgres_history_task
    
    if not chat_history_str and postgres_history:
        chat_history_str = postgres_history
    
    memory_context = ""
    try:
        embed_engine = LLMFactory.get_embedding_engine()
        embedding_str = await get_cached_embedding(embed_engine, user_query)
        
        async with memory_manager.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT file_path, content, metadata, (embedding <=> $1) as distance
                FROM agent_memory
                ORDER BY distance ASC
                LIMIT 5;
                """,
                embedding_str
            )
            memories = [
                {
                    "file_path": r["file_path"],
                    "content": r["content"],
                    "metadata": json.loads(r["metadata"]),
                } for r in rows
            ]
            memory_context = "\n".join([f"[Fragment {m['metadata'].get('chunk_index', 0)} from {m['metadata'].get('file_name', 'Doc')}]: {m['content']}" for m in memories])
    except Exception as e:
        logger.error(f"[L2/L4 Search] Semantic search failed: {e}")

    return {
        "memory_context": memory_context,
        "tool_summary": chat_history_str
    }
