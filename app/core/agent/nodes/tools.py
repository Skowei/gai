import asyncio
import logging
from typing import Dict, Any
from langchain_community.tools import DuckDuckGoSearchRun
from app.core.agent.state import AgentState
from app.core.agent.nodes.utils import get_last_user_message, safe_get_attr
from app.core.memory.postgres import UnifiedMemoryManager

logger = logging.getLogger(__name__)

memory_manager = UnifiedMemoryManager()
web_search_tool = DuckDuckGoSearchRun()


async def execute_mcp_tools_node(state: AgentState) -> Dict[str, Any]:
    """[EXECUTION DOMAIN] Executes operational tools using pristine LLM-formulated keywords."""
    # Safety fallback to prevent crashes if something goes wrong
    target_query = safe_get_attr(state, "search_query", "").strip()
    next_step = safe_get_attr(state, "next_step", "FINISH")
    
    if next_step == "WEB_SEARCH":
        # Validate search query is not empty
        if not target_query:
            logger.warning("[Auto-Web-Search] Empty search query provided, skipping search.")
            return {
                "next_step": "FINISH",
                "tool_summary": "<web_search_results>Error: No search query provided.</web_search_results>",
                "tool_responses": [{"tool": "web_search", "query": "", "status": "failed", "error": "Empty query"}]
            }
        
        logger.info(f"🌐 [Auto-Web-Search] Running live internet crawler for verified query: '{target_query}'")
        try:
            loop = asyncio.get_running_loop()
            search_results = await loop.run_in_executor(None, web_search_tool.run, target_query)
            logger.info("✅ [Auto-Web-Search] External network payload retrieved successfully.")
            
            # Formujemy ustrukturyzowany, uniwersalny blok danych systemowych
            formatted_results = f"<web_search_results>\n{search_results}\n</web_search_results>"
            
            # Zwracamy spójne dane: dociągamy rekord do listy obiektów ORAZ aktualizujemy podsumowanie tekstowe
            return {
                "next_step": "FINISH",
                "tool_summary": formatted_results,
                "tool_responses": [{"tool": "web_search", "query": target_query, "status": "success"}]
            }
        except Exception as err:
            logger.error(f"❌ [Auto-Web-Search Crash] Network interface error: {err}")
            error_msg = "<web_search_results>Error: Network interface failed to retrieve live data.</web_search_results>"
            return {
                "next_step": "FINISH",
                "tool_summary": error_msg,
                "tool_responses": [{"tool": "web_search", "query": target_query, "status": "failed", "error": str(err)}]
            }

    # --- FALLBACK FOR FILE ENGINE ---
    elif next_step == "FILE_ENGINE":
        user_query = get_last_user_message(state)
        session_id = safe_get_attr(state, "session_id", "default_session")
        try:
            rel_file_name = f"knowledge_base/fact_{session_id}.md"
            await memory_manager.save_to_local_notes_and_vector(
                rel_path=rel_file_name,
                content=user_query,
                metadata={"session_id": session_id, "memory_layer": "L3_Internal"}
            )
            return {
                "next_step": "FINISH",
                "tool_summary": "<file_engine_status>Success: Data saved to L3 memory.</file_engine_status>",
                "tool_responses": [{"tool": "file_engine", "status": "success"}]
            }
        except Exception as e:
            logger.error(f"[File Engine Error] Failed to save: {e}")
            return {
                "next_step": "FINISH",
                "tool_summary": f"<file_engine_status>Error: {e}</file_engine_status>",
                "tool_responses": [{"tool": "file_engine", "status": "failed", "error": str(e)}]
            }

    return {"next_step": "FINISH"}
