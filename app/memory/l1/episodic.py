"""
L1: Episodic Memory - Cross-Session Context Manager
Enterprise-grade user profiles, conversation summaries, and long-term preferences.
"""
import json
import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """L1 User Profile - persistent user information"""
    session_id: str
    created_at: float
    last_seen: float
    name: Optional[str] = None
    language: str = "polish"
    preferences: Dict[str, Any] = field(default_factory=dict)
    interests: List[str] = field(default_factory=list)
    total_interactions: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationSummary:
    """L1 Conversation Summary - compressed session memory"""
    session_id: str
    summary: str
    key_topics: List[str]
    timestamp: float
    message_count: int
    duration_minutes: float


class L1EpisodicMemory:
    """
    L1: Episodic Memory Manager
    Manages user profiles, conversation summaries, and cross-session context.
    """
    
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.profile_ttl = 2592000  # 30 days
        self.summary_ttl = 604800   # 7 days
        self.max_summaries = 100    # Max summaries to keep
    
    def _profile_key(self, session_id: str) -> str:
        return f"l1:profile:{session_id}"
    
    def _summary_key(self, session_id: str) -> str:
        return f"l1:summaries:{session_id}"
    
    def _context_key(self, session_id: str) -> str:
        return f"l1:context:{session_id}"
    
    # === User Profile ===
    
    async def get_or_create_profile(self, session_id: str) -> UserProfile:
        """Get existing user profile or create new one."""
        key = self._profile_key(session_id)
        data = await self.redis.get(key)
        
        if data:
            profile = UserProfile(**json.loads(data))
            profile.last_seen = time.time()
            await self._save_profile(profile)  # BUGFIX: persist last_seen update
            return profile
        
        profile = UserProfile(
            session_id=session_id,
            created_at=time.time(),
            last_seen=time.time()
        )
        await self._save_profile(profile)
        logger.info(f"[L1] Created new user profile: {session_id}")
        return profile
    
    async def _save_profile(self, profile: UserProfile):
        """Persist user profile to Redis."""
        key = self._profile_key(profile.session_id)
        await self.redis.setex(key, self.profile_ttl, json.dumps(asdict(profile)))
    
    async def update_profile(self, session_id: str, **kwargs):
        """Update user profile fields (does NOT increment interactions — use record_interaction)."""
        profile = await self.get_or_create_profile(session_id)
        
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        profile.last_seen = time.time()
        await self._save_profile(profile)
        logger.info(f"[L1] Updated profile: {session_id}")
    
    async def set_user_name(self, session_id: str, name: str):
        """Set user name in profile."""
        await self.update_profile(session_id, name=name)
    
    async def record_interaction(self, session_id: str):
        """
        Record one chat interaction (single source of truth for total_interactions).
        Called exactly once per chat request (fresh or cache-hit).
        """
        profile = await self.get_or_create_profile(session_id)
        profile.total_interactions += 1
        profile.last_seen = time.time()
        await self._save_profile(profile)
    
    async def set_language(self, session_id: str, language_code: str):
        """Sync detected language (ISO 639-1) into profile. No interaction increment."""
        profile = await self.get_or_create_profile(session_id)
        if profile.language != language_code:
            profile.language = language_code
            await self._save_profile(profile)
            logger.info(f"[L1] Language synced to '{language_code}': {session_id}")
    
    async def set_language(self, session_id: str, language: str):
        """Set preferred language."""
        await self.update_profile(session_id, language=language)
    
    async def add_interest(self, session_id: str, interest: str):
        """Add user interest."""
        profile = await self.get_or_create_profile(session_id)
        if interest not in profile.interests:
            profile.interests.append(interest)
            await self._save_profile(profile)
    
    async def get_profile(self, session_id: str) -> Optional[UserProfile]:
        """Get user profile."""
        key = self._profile_key(session_id)
        data = await self.redis.get(key)
        if data:
            return UserProfile(**json.loads(data))
        return None
    
    # === Conversation Summaries ===
    
    async def save_conversation_summary(self, session_id: str, summary: str,
                                       key_topics: List[str], message_count: int,
                                       duration_minutes: float):
        """Save conversation summary for future reference."""
        summary_obj = ConversationSummary(
            session_id=session_id,
            summary=summary,
            key_topics=key_topics,
            timestamp=time.time(),
            message_count=message_count,
            duration_minutes=duration_minutes
        )
        
        key = self._summary_key(session_id)
        await self.redis.lpush(key, json.dumps(asdict(summary_obj)))
        await self.redis.ltrim(key, 0, self.max_summaries - 1)
        await self.redis.expire(key, self.summary_ttl)
        logger.info(f"[L1] Saved conversation summary: {session_id}")
    
    async def get_recent_summaries(self, session_id: str, limit: int = 5) -> List[ConversationSummary]:
        """Get recent conversation summaries."""
        key = self._summary_key(session_id)
        summaries = await self.redis.lrange(key, 0, limit - 1)
        return [ConversationSummary(**json.loads(s)) for s in summaries]
    
    # === Cross-Session Context ===
    
    async def save_cross_session_context(self, session_id: str, context: Dict[str, Any]):
        """Save context that persists across sessions."""
        key = self._context_key(session_id)
        await self.redis.setex(key, self.profile_ttl, json.dumps(context))
    
    async def get_cross_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get cross-session context."""
        key = self._context_key(session_id)
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return {}
    
    # === Combined Context for LLM ===
    
    async def get_enriched_context(self, session_id: str) -> Dict[str, Any]:
        """
        Get enriched context combining profile, summaries, and cross-session data.
        This is what gets injected into LLM prompts.
        """
        profile = await self.get_profile(session_id)
        summaries = await self.get_recent_summaries(session_id, limit=3)
        cross_session = await self.get_cross_session_context(session_id)
        
        context = {
            "user": {
                "name": profile.name if profile else None,
                "language": profile.language if profile else "polish",
                "interests": profile.interests if profile else [],
                "total_interactions": profile.total_interactions if profile else 0
            },
            "recent_topics": [],
            "cross_session": cross_session
        }
        
        # Extract key topics from recent summaries
        for summary in summaries:
            context["recent_topics"].extend(summary.key_topics)
        
        # Deduplicate topics
        context["recent_topics"] = list(set(context["recent_topics"]))[:10]
        
        return context
    
    # === Stats ===
    
    async def get_stats(self, session_id: str) -> Dict[str, Any]:
        """Get L1 memory statistics."""
        profile = await self.get_profile(session_id)
        summaries = await self.get_recent_summaries(session_id)
        
        return {
            "has_profile": profile is not None,
            "user_name": profile.name if profile else None,
            "language": profile.language if profile else None,
            "interests": profile.interests if profile else [],
            "total_interactions": profile.total_interactions if profile else 0,
            "conversation_summaries": len(summaries),
            "profile_age_days": round((time.time() - profile.created_at) / 86400, 1) if profile else None
        }
