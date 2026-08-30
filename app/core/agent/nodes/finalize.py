import json
import logging
import re
import time
from typing import Dict, Any
from app.core.agent.state import AgentState
from app.core.agent.nodes.utils import get_last_user_message, safe_get_attr
from app.services.llm_service import LLMFactory
from app.core.redis import redis_client  # shared singleton (1 connection total)
from app.api.deps import memory_manager  # shared singleton (1 pool total)
from app.memory.l1.episodic import L1EpisodicMemory
from app.core.language import detect_language, get_language_directive

logger = logging.getLogger(__name__)

l1_memory = L1EpisodicMemory(redis_client)


async def reflect_and_finalize_node(state: AgentState) -> Dict[str, Any]:
    """[FINAL SYNTHESIS NODE] Generate response and update memory layers."""
    user_query = get_last_user_message(state)
    text_llm = LLMFactory.get_model_by_role("text")
    session_id = safe_get_attr(state, "session_id", "default_session")
    redis_key = f"chat_session:{session_id}"
    session_start = time.time()
    
    raw_tool_summary = safe_get_attr(state, "tool_summary", "") or ""
    is_web_search = "<web_search_results>" in str(raw_tool_summary)
    
    if is_web_search:
        history_context = "Bypassed to maintain focus on fresh live search data."
        local_rag_context = "Bypassed to prioritize external world facts."
        web_context = raw_tool_summary
    else:
        history_context = raw_tool_summary
        local_rag_context = safe_get_attr(state, "memory_context", "")
        web_context = "No live web search data requested for this step."

    user_context = safe_get_attr(state, "user_context", "")
    user_section = ""
    if user_context and isinstance(user_context, dict):
        user = user_context.get("user", {})
        if user.get("name"):
            user_section = f"\n[USER PROFILE]\nName: {user.get('name')}\nInterests: {', '.join(user.get('interests', []))}\n"
    
    # Language stability: deterministic Language ID (lingua: 75 languages,
    # seeded langdetect fallback). The directive anchors the NATIVE language
    # name (stronger signal for 8B local models); when detection fails
    # (too short / ambiguous) it degrades to a deterministic mirror rule.
    # This works for ANY language - not hardcoded to a single one.
    query_lang = detect_language(user_query)
    language_directive = get_language_directive(query_lang)
    logger.debug(f"[LID] detected language: {query_lang}")

    prompt = f"""{language_directive}

You are a professional, helpful, and highly adaptable AI Assistant operating in an advanced Enterprise architecture.
Your main goal is to answer the user's current query in a natural, fluid, direct, and concise manner.
Never output any internal execution logs, python exceptions, node names, or technical tags in your final answer.
Base your reasoning strictly on the provided context layers below.
{user_section}
[CONVERSATION HISTORY (L0 Session Cache)]
{history_context}

[LOCAL KNOWLEDGE CONTEXT (RAG L2/L4)]
{local_rag_context}

[EXTERNAL EXECUTION CONTEXT (Live Tool Outputs)]
{web_context}

User's current query: {user_query}

FINAL REMINDER: {language_directive}
Response:"""
    
    response = await text_llm.ainvoke(prompt)
    response_text = response if isinstance(response, str) else getattr(response, "content", str(response))
    
    # L0: Update session cache
    try:
        history_json = await redis_client.get(redis_key)
        current_history = json.loads(history_json) if history_json else []
        current_history.extend([
            {"role": "User", "content": user_query},
            {"role": "Assistant", "content": response_text}
        ])
        await redis_client.setex(redis_key, 7200, json.dumps(current_history))
    except Exception as re_err:
        logger.warning(f"[L0 Cache Error] {re_err}")

    # L2: Archive interaction
    try:
        await memory_manager.log_chat_interaction(session_id, user_query, response_text)
    except Exception as e:
        logger.error(f"[L2 Archive Error] {e}")
    
    # L1: Save conversation summary
    try:
        key_topics = []
        if "<web_search_results>" in raw_tool_summary:
            key_topics.append("web_search")
        if local_rag_context and local_rag_context != "Bypassed to prioritize external world facts.":
            key_topics.append("local_knowledge")
        
        summary_text = f"Q: {user_query[:100]}... A: {response_text[:100]}..."
        await l1_memory.save_conversation_summary(
            session_id=session_id,
            summary=summary_text,
            key_topics=key_topics if key_topics else ["general"],
            message_count=len(current_history) if 'current_history' in locals() else 2,
            duration_minutes=(time.time() - session_start) / 60
        )
    except Exception as e:
        logger.warning(f"[L1 Summary Error] {e}")
    
    # L1: Auto-detect user name
    try:
        query_lower = user_query.lower()
        for phrase in ["nazywam się ", "jestem ", "my name is ", "i'm ", "im "]:
            if phrase in query_lower:
                name = user_query.split(phrase)[-1].strip().split()[0].rstrip(".,!")
                if len(name) > 1 and name[0].isupper():
                    await l1_memory.set_user_name(session_id, name)
                    logger.info(f"[L1 Profile] Detected user name: {name}")
                    break
    except Exception as e:
        logger.debug(f"[L1 Name Detection] {e}")
        
    return {"final_response": response_text}
