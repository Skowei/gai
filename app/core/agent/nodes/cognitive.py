import json
import re
from typing import Dict, Any
from app.core.agent.state import AgentState
from app.core.llm_factory import LLMFactory

def _get_last_user_message(state: AgentState) -> str:
    messages = getattr(state, "messages", []) if not isinstance(state, dict) else state.get("messages", [])
    if not messages: return ""
    last_message = messages[-1]
    if isinstance(last_message, str): return last_message
    if isinstance(last_message, dict): return str(last_message.get("content", ""))
    if hasattr(last_message, "content"): return str(last_message.content)
    return str(last_message)

async def cognitive_core_node(state: AgentState) -> Dict[str, Any]:
    """[DECISION CORE L0] Generates dynamic optimized search queries via LLM reasoning."""
    user_query = _get_last_user_message(state)
    tool_summary = getattr(state, "tool_summary", "") or ""
    reasoning_llm = LLMFactory.get_model_by_role("reasoning")
    
    system_prompt = f"""
    You are the central cognitive processor of an Enterprise AI System (L0-L4).
    Your task is to analyze the user's query, available context, and determine the next execution step.

    AVAILABLE EXECUTION DOMAINS (Tools):
    1. 'FILE_ENGINE': Choose this ONLY when the user explicitly provides NEW personal facts, preferences, or technical data that must be permanently memorized for the first time.
    2. 'WEB_SEARCH': Choose this when the query requires real-time internet data. You MUST formulate a clean, optimized search query (keywords only, without conversational fluff) in the 'search_query' field.
    3. 'FINISH': Choose this when the user is asking to RECALL, RETRIEVE, READ, or VERIFY any existing information about their identity, name, profile, preferences, or previously shared data. Checking existing information is a strict READ operation—do NOT trigger FILE_ENGINE or WEB_SEARCH for identity lookup or profiling queries. Also choose this for regular conversations, greetings, or direct answers.

    Local knowledge context (RAG L2/L4):
    {state.memory_context}

    Current loop history:
    {tool_summary}

    You must reply EXCLUSIVELY with a raw, valid JSON object. No thinking tags, no markdown blocks.
    RESPONSE FORMAT FOR WEB_SEARCH:
    {{"reasoning_plan": "Why search is needed", "next_step": "WEB_SEARCH", "search_query": "optimized search keywords here"}}
    
    RESPONSE FORMAT FOR OTHERS:
    {{"reasoning_plan": "Justification of why you choose FILE_ENGINE or FINISH", "next_step": "FILE_ENGINE_OR_FINISH", "search_query": ""}}
    """

    prompt_input = f"SYSTEM: {system_prompt}\n\nUSER: {user_query}"
    response = await reasoning_llm.ainvoke(prompt_input)
    response_text = response if isinstance(response, str) else getattr(response, "content", str(response))
    
    clean_content = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
    clean_content = re.sub(r"```json", "", clean_content, flags=re.IGNORECASE)
    clean_content = re.sub(r"```", "", clean_content).strip()
    
    try:
        decision = json.loads(clean_content)
        print(f"🧠 [Brain L0] Plan: {decision.get('reasoning_plan')} -> Step: {decision.get('next_step')} -> Query: {decision.get('search_query')}")
        return {
            "reason_response": decision.get("reasoning_plan", ""),
            "next_step": decision.get("next_step", "FINISH"),
            "search_query": decision.get("search_query", "")
        }
    except Exception:
        try:
            json_match = re.search(r"\{.*\}", clean_content, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group(0))
                return {
                    "reason_response": decision.get("reasoning_plan", ""),
                    "next_step": decision.get("next_step", "FINISH"),
                    "search_query": decision.get("search_query", "")
                }
        except Exception:
            pass
        return {"next_step": "FINISH", "reason_response": "Fallback", "search_query": ""}
