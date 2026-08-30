"""
L0: Working Memory - Session Context Manager
Enterprise-grade session state management with token tracking.
"""
import json
import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """L0 Working Memory - current session state"""
    session_id: str
    created_at: float
    last_activity: float
    message_count: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    current_context_tokens: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class L0WorkingMemory:
    """
    L0: Working Memory Manager
    Manages active session context with token tracking and TTL.
    """
    
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.ttl = 7200  # 2 hours session TTL
        self.max_context_tokens = 4000  # Max tokens for context window
        self.max_messages = 50  # Max messages in session history
    
    def _key(self, session_id: str) -> str:
        return f"l0:session:{session_id}"
    
    def _messages_key(self, session_id: str) -> str:
        return f"l0:messages:{session_id}"
    
    async def get_or_create_session(self, session_id: str) -> SessionContext:
        """Get existing session or create new one."""
        key = self._key(session_id)
        data = await self.redis.get(key)
        
        if data:
            ctx_data = json.loads(data)
            ctx = SessionContext(**ctx_data)
            ctx.last_activity = time.time()
            return ctx
        
        ctx = SessionContext(
            session_id=session_id,
            created_at=time.time(),
            last_activity=time.time()
        )
        await self._save_session(ctx)
        logger.info(f"[L0] Created new session: {session_id}")
        return ctx
    
    async def _save_session(self, ctx: SessionContext):
        """Persist session context to Redis."""
        key = self._key(ctx.session_id)
        await self.redis.setex(key, self.ttl, json.dumps(asdict(ctx)))
    
    async def add_message(self, session_id: str, role: str, content: str, 
                         tokens_in: int = 0, tokens_out: int = 0):
        """Add message to session history."""
        ctx = await self.get_or_create_session(session_id)
        
        ctx.message_count += 1
        ctx.total_tokens_in += tokens_in
        ctx.total_tokens_out += tokens_out
        ctx.last_activity = time.time()
        
        messages_key = self._messages_key(session_id)
        message = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out
        }
        
        await self.redis.rpush(messages_key, json.dumps(message))
        await self.redis.ltrim(messages_key, -self.max_messages, -1)
        await self.redis.expire(messages_key, self.ttl)
        
        await self._save_session(ctx)
    
    async def get_messages(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent messages from session history."""
        messages_key = self._messages_key(session_id)
        messages = await self.redis.lrange(messages_key, -limit, -1)
        return [json.loads(m) for m in messages]
    
    async def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """Get current session context with token usage."""
        key = self._key(session_id)
        data = await self.redis.get(key)
        if data:
            return SessionContext(**json.loads(data))
        return None
    
    async def update_metadata(self, session_id: str, metadata: Dict[str, Any]):
        """Update session metadata."""
        ctx = await self.get_or_create_session(session_id)
        ctx.metadata.update(metadata)
        await self._save_session(ctx)
    
    async def get_context_for_llm(self, session_id: str) -> Dict[str, Any]:
        """Prepare context payload for LLM prompt."""
        ctx = await self.get_session_context(session_id)
        messages = await self.get_messages(session_id)
        
        if not ctx:
            return {"messages": [], "token_usage": {}, "metadata": {}}
        
        return {
            "messages": messages[-10:],
            "token_usage": {
                "total_tokens_in": ctx.total_tokens_in,
                "total_tokens_out": ctx.total_tokens_out,
                "message_count": ctx.message_count
            },
            "metadata": ctx.metadata
        }
    
    async def clear_session(self, session_id: str):
        """Clear all session data."""
        await self.redis.delete(self._key(session_id), self._messages_key(session_id))
        logger.info(f"[L0] Cleared session: {session_id}")
    
    async def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs."""
        keys = []
        async for key in self.redis.scan_iter(match="l0:session:*"):
            session_id = key.decode().replace("l0:session:", "")
            keys.append(session_id)
        return keys
    
    async def get_stats(self, session_id: str) -> Dict[str, Any]:
        """Get session statistics."""
        ctx = await self.get_session_context(session_id)
        if not ctx:
            return {"error": "Session not found"}
        
        return {
            "session_id": ctx.session_id,
            "duration_minutes": round((time.time() - ctx.created_at) / 60, 1),
            "message_count": ctx.message_count,
            "total_tokens_in": ctx.total_tokens_in,
            "total_tokens_out": ctx.total_tokens_out,
            "metadata": ctx.metadata
        }
