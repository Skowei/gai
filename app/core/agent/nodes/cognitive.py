import json
import logging
import re
from typing import Dict, Any
from app.core.agent.state import AgentState
from app.core.agent.nodes.utils import get_last_user_message, safe_get_attr
from app.services.llm_service import LLMFactory

logger = logging.getLogger(__name__)


async def cognitive_core_node(state: AgentState) -> Dict[str, Any]:
    """[DECISION CORE L0] LLM decides next step based on context."""
    user_query = get_last_user_message(state)
    tool_summary = safe_get_attr(state, "tool_summary", "") or ""
    memory_context = safe_get_attr(state, "memory_context", "")
    reasoning_llm = LLMFactory.get_model_by_role("reasoning")
    
    system_prompt = f"""
You are the central cognitive processor of an Enterprise AI System (L0-L4).
Analyze the user's query and available context to determine the next step.

AVAILABLE EXECUTION DOMAINS:
1. 'WEB_SEARCH': Real-time internet data (DuckDuckGo)
2. 'ARXIV_SEARCH': Academic papers and research articles
3. 'WIKI_SEARCH': Wikipedia knowledge base
4. 'BROWSER_AUTOMATION': Web scraping, forms, screenshots (PinchTab)
5. 'CODE_EXECUTION': Run Python code for calculations/analysis
6. 'FILE_ENGINE': Save NEW personal facts/preferences to memory
7. 'FINISH': For RECALL, RETRIEVE, READ operations or casual conversation

Local knowledge context (RAG L2/L4):
{memory_context}

Current loop history:
{tool_summary}

Reply with raw JSON only. No markdown, no thinking tags.

Response formats:
{{"reasoning_plan": "...", "next_step": "WEB_SEARCH", "search_query": "keywords"}}
{{"reasoning_plan": "...", "next_step": "ARXIV_SEARCH", "search_query": "keywords"}}
{{"reasoning_plan": "...", "next_step": "WIKI_SEARCH", "search_query": "keywords"}}
{{"reasoning_plan": "...", "next_step": "BROWSER_AUTOMATION", "browser_action": "navigate|click|fill|extract|snapshot|screenshot", "browser_url": "https://...", "browser_ref": "e5", "browser_text": "text"}}
{{"reasoning_plan": "...", "next_step": "CODE_EXECUTION", "code": "print('hello')"}}
{{"reasoning_plan": "...", "next_step": "FILE_ENGINE", "search_query": "fact to save"}}
{{"reasoning_plan": "...", "next_step": "FINISH"}}
"""

    prompt_input = f"SYSTEM: {system_prompt}\n\nUSER: {user_query}"
    response = await reasoning_llm.ainvoke(prompt_input)
    response_text = response if isinstance(response, str) else getattr(response, "content", str(response))
    
    # Clean response
    clean_content = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
    clean_content = re.sub(r"```json", "", clean_content, flags=re.IGNORECASE)
    clean_content = re.sub(r"```", "", clean_content).strip()
    
    try:
        decision = json.loads(clean_content)
        logger.info(f"[Brain] {decision.get('reasoning_plan')} -> {decision.get('next_step')}")
        return _parse_decision(decision)
    except json.JSONDecodeError:
        try:
            json_match = re.search(r"\{.*\}", clean_content, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group(0))
                return _parse_decision(decision)
        except (json.JSONDecodeError, AttributeError):
            pass
        return {"next_step": "FINISH", "reason_response": "Fallback", "search_query": ""}
    except Exception as e:
        logger.error(f"[Brain] Error: {e}")
        return {"next_step": "FINISH", "reason_response": "Fallback", "search_query": ""}


def _parse_decision(decision: dict) -> dict:
    """Parse LLM decision into state updates."""
    base = {
        "reason_response": decision.get("reasoning_plan", ""),
        "next_step": decision.get("next_step", "FINISH"),
        "search_query": decision.get("search_query", ""),
    }
    
    # Add browser fields if present
    if "browser_action" in decision:
        base["browser_action"] = decision["browser_action"]
        base["browser_url"] = decision.get("browser_url", "")
        base["browser_ref"] = decision.get("browser_ref", "")
        base["browser_text"] = decision.get("browser_text", "")
    
    # Add code field if present
    if "code" in decision:
        base["code"] = decision["code"]
    
    return base
