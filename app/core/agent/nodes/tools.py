import logging
from typing import Dict, Any
from app.core.agent.state import AgentState
from app.core.agent.tools import registry
from app.core.agent.nodes.utils import safe_get_attr

logger = logging.getLogger(__name__)


async def execute_mcp_tools_node(state: AgentState) -> Dict[str, Any]:
    """[EXECUTION DOMAIN - ENTERPRISE] Routes to tool via ToolRegistry."""
    next_step = safe_get_attr(state, "next_step", "FINISH")
    
    tool_mapping = {
        "WEB_SEARCH": "web_search",
        "ARXIV_SEARCH": "arxiv_search",
        "WIKI_SEARCH": "wikipedia_search",
        "BROWSER_AUTOMATION": "browser",
        "CODE_EXECUTION": "code_executor",
        "FILE_ENGINE": "file_engine",
    }
    
    tool_name = tool_mapping.get(next_step)
    if not tool_name:
        logger.info(f"[Tools] No tool mapping for '{next_step}', routing to FINISH")
        return {"next_step": "FINISH"}
    
    param_extractors = {
        "web_search": lambda s: {"query": safe_get_attr(s, "search_query", "")},
        "arxiv_search": lambda s: {"query": safe_get_attr(s, "search_query", "")},
        "wikipedia_search": lambda s: {"query": safe_get_attr(s, "search_query", "")},
        "browser": lambda s: {
            "action": safe_get_attr(s, "browser_action", "navigate"),
            "url": safe_get_attr(s, "browser_url", ""),
            "ref": safe_get_attr(s, "browser_ref", ""),
            "text": safe_get_attr(s, "browser_text", ""),
        },
        "code_executor": lambda s: {"code": safe_get_attr(s, "code", "")},
        "file_engine": lambda s: {
            "content": safe_get_attr(s, "search_query", "") or safe_get_attr(s, "user_query", ""),
            "session_id": safe_get_attr(s, "session_id", "default"),
        },
    }
    
    params = param_extractors.get(tool_name, lambda s: {})(state)
    logger.info(f"[Tools] Executing '{tool_name}' with params: {list(params.keys())}")
    
    result = await registry.execute(tool_name, **params)
    tool_summary = result.to_xml()
    
    return {
        "next_step": "FINISH",
        "tool_summary": tool_summary,
        "tool_responses": [{
            "tool": result.tool_name,
            "status": result.status.value,
            "duration_ms": round(result.duration_ms, 2)
        }]
    }
