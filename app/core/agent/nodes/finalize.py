import json
from typing import Dict, Any
import redis.asyncio as aioredis
from app.core.agent.state import AgentState
from app.core.llm_factory import LLMFactory
from app.core.memory.postgres import UnifiedMemoryManager
from app.core.config import settings

memory_manager = UnifiedMemoryManager()
redis_client = aioredis.from_url(getattr(settings, "redis_url", "redis://redis:6379/0"), decode_responses=True)

def _get_last_user_message(state: AgentState) -> str:
    messages = getattr(state, "messages", []) if not isinstance(state, dict) else state.get("messages", [])
    if not messages: return ""
    last_message = messages[-1]
    if hasattr(last_message, "content"): return str(last_message.content)
    return str(last_message)

async def reflect_and_finalize_node(state: AgentState) -> Dict[str, Any]:
    """[FINAL SYNTHESIS NODE] Dynamically handles response context based on active tools."""
    user_query = _get_last_user_message(state)
    text_llm = LLMFactory.get_model_by_role("text")
    session_id = state.session_id
    redis_key = f"chat_session:{session_id}"
    
    # 🔍 Sprawdzamy zawartość szyny danych narzędziowych
    raw_tool_summary = getattr(state, "tool_summary", "") or ""
    is_web_search = "<web_search_results>" in str(raw_tool_summary)
    
    # 🛡️ PANCERNA SELEKCJA KONTEKSTU (Ochrona przed zapychaniem wątków i halucynacjami)
    if is_web_search:
        # Jeśli szukamy w sieci, izolujemy kontekst - ukrywamy starą historię przed Llamą
        history_context = "Bypassed to maintain focus on fresh live search data."
        local_rag_context = "Bypassed to prioritize external world facts."
        web_context = raw_tool_summary
    else:
        # Standardowy tryb lokalny / rozmowy
        history_context = raw_tool_summary
        local_rag_context = state.memory_context
        web_context = "No live web search data requested for this step."

    # Krystalicznie czysty, anglojęzyczny kontekst strukturalny systemu Enterprise
    prompt = f"""
    You are a professional, helpful, and highly adaptable AI Assistant operating in an advanced Enterprise architecture.
    Your main goal is to answer the user's current query in a natural, fluid, direct, and concise manner.
    Never output any internal execution logs, python exceptions, node names, or technical tags in your final answer.
    Base your reasoning strictly on the provided context layers below.

    [CONVERSATION HISTORY (L1 Session Cache)]
    {history_context}

    [LOCAL KNOWLEDGE CONTEXT (RAG L2/L4)]
    {local_rag_context}

    [EXTERNAL EXECUTION CONTEXT (Live Tool Outputs)]
    {web_context}

    User's current query: {user_query}
    
    CRITICAL SPECIFICATION: You must analyze the language of the user's current query and generate your entire final response using the EXACT SAME LANGUAGE (e.g., if user writes in Polish, respond in Polish; if in English, respond in English).
    Response:"""
    
    response = await text_llm.ainvoke(prompt)
    response_text = response if isinstance(response, str) else getattr(response, "content", str(response))
    
    # --- WRITE-THROUGH CACHE: Aktualizacja pamięci krótkoterminowej L1 (Redis RAM) ---
    try:
        history_json = await redis_client.get(redis_key)
        current_history = json.loads(history_json) if history_json else []
        current_history.extend([
            {"role": "User", "content": user_query},
            {"role": "Assistant", "content": response_text}
        ])
        await redis_client.setex(redis_key, 7200, json.dumps(current_history))
    except Exception as re_err:
        print(f"⚠️ [Memory L1 Sync Error] {re_err}")

    # --- ARCHIWIZACJA: Trwały zapis zapasowy w PostgreSQL L2 ---
    try:
        await memory_manager.log_chat_interaction(session_id, user_query, response_text)
    except Exception:
        pass
        
    return {"final_response": response_text}
