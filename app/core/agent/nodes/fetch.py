import json
import logging
from typing import Dict, Any
import redis.asyncio as aioredis
from app.core.agent.state import AgentState
from app.core.agent.nodes.utils import get_last_user_message, safe_get_attr
from app.core.memory.postgres import UnifiedMemoryManager
from app.core.config import settings

logger = logging.getLogger(__name__)

memory_manager = UnifiedMemoryManager()
redis_client = aioredis.from_url(getattr(settings, "redis_url", "redis://redis:6379/0"), decode_responses=True)


async def fetch_memory_node(state: AgentState) -> Dict[str, Any]:
    """Łączy dane z L1 (Redis Cache) oraz skanuje wektorowo L2/L4 za pomocą Postgresa."""
    user_query = get_last_user_message(state)
    session_id = safe_get_attr(state, "session_id", "default_session")
    redis_key = f"chat_session:{session_id}"
    
    chat_history_str = ""
    try:
        history_json = await redis_client.get(redis_key)
        if history_json:
            messages_list = json.loads(history_json)
            chat_history_str = "\n".join([f"{m['role']}: {m['content']}" for m in messages_list])
            logger.info(f"⚡ [Pamięć L1] Trafiono w Cache RAM dla sesji: {session_id}")
        else:
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
                    chat_history_str = "\n".join([f"{m['role']}: {m['content']}" for m in redis_payload])
                    await redis_client.setex(redis_key, 7200, json.dumps(redis_payload))
    except Exception as e:
        logger.error(f"⚠️ [Pamięć L1 Błąd] Szyna danych unieruchomiona: {e}")

    memory_context = ""
    try:
        memories = await memory_manager.semantic_search(user_query, limit=5)
        memory_context = "\n".join([f"[Fragment {m['metadata'].get('chunk_index', 0)} from {m['metadata'].get('file_name', 'Doc')}]: {m['content']}" for m in memories])
    except Exception as e:
        logger.error(f"[Pamięć L2/L4 Błąd] Semantic search failed: {e}")

    return {
        "memory_context": memory_context,
        "tool_summary": chat_history_str
    }
