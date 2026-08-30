import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.agent.brain import agent_brain
from app.services.cache_service import get_cached_response, set_cached_response
from app.api.deps import redis_client
from app.memory import L0WorkingMemory, L1EpisodicMemory
from app.core.language import detect_language
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

# Initialize L0 and L1 memory managers
l0_memory = L0WorkingMemory(redis_client)
l1_memory = L1EpisodicMemory(redis_client)

router = APIRouter(prefix="/v1", tags=["Czat Vue 3"])


async def _user_payload(session_id: str, fallback: dict) -> dict:
    """Fresh L1 user data for API response (accurate AFTER interaction recording)."""
    profile = await l1_memory.get_profile(session_id)
    if profile:
        return {
            "name": profile.name,
            "language": profile.language,
            "interests": profile.interests,
            "total_interactions": profile.total_interactions,
        }
    return fallback


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"


@router.post("/chat")
async def chat_endpoint(payload: ChatRequest):
    """Główny punkt wejścia dla aplikacji Vue 3 oraz Postmana."""
    try:
        # L0: Get or create session context
        session_ctx = await l0_memory.get_or_create_session(payload.session_id)
        
        # L1: Get enriched context (user profile, recent topics)
        enriched_context = await l1_memory.get_enriched_context(payload.session_id)
        
        # Check hybrid cache first (simple cache without context)
        # Defensive: legacy/malformed cache entries (missing 'response' key) are treated as a miss
        cached = await get_cached_response(payload.session_id, payload.message)
        if cached and isinstance(cached, dict) and cached.get("response"):
            # L0: Track cache hit
            await l0_memory.add_message(
                payload.session_id, "user", payload.message, tokens_in=0
            )
            await l0_memory.add_message(
                payload.session_id, "assistant", cached["response"], tokens_out=0
            )
            # L1: A cache hit is still a real interaction
            await l1_memory.record_interaction(payload.session_id)
            return {
                "status": "success",
                "session_id": payload.session_id,
                "response": cached["response"],
                "tool_summary": cached.get("tool_summary", ""),
                "plan_executed": cached.get("reason_response", ""),
                "from_cache": True,
                "cache_time": cached.get("cache_time", ""),
                "user": await _user_payload(payload.session_id, enriched_context.get("user", {}))
            }
        
        # Get messages from L0 for graph state
        recent_messages = await l0_memory.get_messages(payload.session_id, limit=10)
        
        # Prepare initial state for LangGraph
        initial_state = {
            "messages": [HumanMessage(content=payload.message)],
            "session_id": payload.session_id,
            "system_instructions": "Jesteś zaawansowanym, autonomicznym ekosystemem AI.",
            "user_context": enriched_context
        }
        
        # Wywołanie maszyny stanów LangGraph
        final_state = await agent_brain.ainvoke(initial_state)
        
        response_text = final_state.get("final_response", "Brak odpowiedzi silnika.")
        
        # L0: Track the interaction
        await l0_memory.add_message(
            payload.session_id, "user", payload.message,
            tokens_in=len(payload.message.split())
        )
        await l0_memory.add_message(
            payload.session_id, "assistant", response_text,
            tokens_out=len(response_text.split())
        )
        
        # L1: Record interaction (single source of truth) + sync detected language
        await l1_memory.record_interaction(payload.session_id)
        detected_lang = detect_language(payload.message)
        if detected_lang:
            await l1_memory.set_language(payload.session_id, detected_lang)
        
        # Cache the response for future use (curated payload only - NOT raw graph state)
        cache_payload = {
            "response": response_text,
            "tool_summary": final_state.get("tool_summary", ""),
            "reason_response": final_state.get("reason_response", ""),
            "cache_time": datetime.now().isoformat(),
        }
        await set_cached_response(
            payload.session_id,
            payload.message,
            cache_payload,
            ttl=300  # 5 minutes
        )
        
        response_data = {
            "status": "success",
            "session_id": payload.session_id,
            "plan_executed": final_state.get("reason_response", ""),
            "tool_summary": final_state.get("tool_summary", ""),
            "response": response_text,
            "from_cache": False,
            "user": await _user_payload(payload.session_id, enriched_context.get("user", {}))
        }
        
        return response_data
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Błąd jądra grafu: {str(e)}")


@router.get("/session/{session_id}/stats")
async def session_stats(session_id: str):
    """Get L0 session statistics."""
    try:
        stats = await l0_memory.get_stats(session_id)
        return {"status": "success", "l0_session": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/profile")
async def user_profile(session_id: str):
    """Get L1 user profile."""
    try:
        profile = await l1_memory.get_profile(session_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {
            "status": "success",
            "profile": {
                "name": profile.name,
                "language": profile.language,
                "interests": profile.interests,
                "total_interactions": profile.total_interactions
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}/profile")
async def update_profile(session_id: str, profile_data: dict):
    """Update L1 user profile."""
    try:
        await l1_memory.update_profile(session_id, **profile_data)
        return {"status": "success", "message": "Profile updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
