import asyncio
from typing import Dict, Any
from langchain_community.tools import DuckDuckGoSearchRun
from app.core.agent.state import AgentState
from app.core.memory.postgres import UnifiedMemoryManager

memory_manager = UnifiedMemoryManager()
web_search_tool = DuckDuckGoSearchRun()

async def execute_mcp_tools_node(state: AgentState) -> Dict[str, Any]:
    """[EXECUTION DOMAIN] Executes operational tools using pristine LLM-formulated keywords."""
    # Safety fallback to prevent crashes if something goes wrong
    target_query = getattr(state, "search_query", "").strip()
    
    if state.next_step == "WEB_SEARCH":
        print(f"🌐 [Auto-Web-Search] Running live internet crawler for verified query: '{target_query}'")
        try:
            loop = asyncio.get_running_loop()
            search_results = await loop.run_in_executor(None, web_search_tool.run, target_query)
            print("✅ [Auto-Web-Search] External network payload retrieved successfully.")
            
            # Formujemy ustrukturyzowany, uniwersalny blok danych systemowych
            formatted_results = f"<web_search_results>\n{search_results}\n</web_search_results>"
            
            # Zwracamy spójne dane: dociągamy rekord do listy obiektów ORAZ aktualizujemy podsumowanie tekstowe
            return {
                "next_step": "FINISH",
                "tool_summary": formatted_results,
                "tool_responses": [{"tool": "web_search", "query": target_query, "status": "success"}]
            }
        except Exception as err:
            print(f"❌ [Auto-Web-Search Crash] Network interface error: {err}")
            error_msg = "<web_search_results>Error: Network interface failed to retrieve live data.</web_search_results>"
            return {
                "next_step": "FINISH",
                "tool_summary": error_msg,
                "tool_responses": [{"tool": "web_search", "query": target_query, "status": "failed", "error": str(err)}]
            }

    # --- FALLBACK FOR FILE ENGINE ---
    elif state.next_step == "FILE_ENGINE":
        messages = getattr(state, "messages", [])
        user_query = messages[-1].content if messages else ""
        try:
            rel_file_name = f"knowledge_base/fact_{state.session_id}.md"
            await memory_manager.save_to_local_notes_and_vector(
                rel_path=rel_file_name,
                content=user_query,
                metadata={"session_id": state.session_id, "memory_layer": "L3_Internal"}
            )
            return {
                "next_step": "FINISH",
                "tool_summary": "<file_engine_status>Success: Data saved to L3 memory.</file_engine_status>",
                "tool_responses": [{"tool": "file_engine", "status": "success"}]
            }
        except Exception as e:
            return {
                "next_step": "FINISH",
                "tool_summary": f"<file_engine_status>Error: {e}</file_engine_status>",
                "tool_responses": [{"tool": "file_engine", "status": "failed", "error": str(e)}]
            }

    return {"next_step": "FINISH"}
