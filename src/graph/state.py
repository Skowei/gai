"""
=============================================================================
AI Ecosystem V2.0 - LangGraph State
Stan workflowu agenta AI (memory -> reasoning -> tools -> response)
=============================================================================
"""

from typing import TypedDict, List, Annotated, Optional, Any
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Stan workflowu agenta AI z rozszerzeniami o pamięć i narzędzia."""

    # =============================================================================
    # PAMIĘĆ AGENTA (L0-L3 z MemoryClient)
    # =============================================================================
    memory_data: dict = {}          # Dane z Redis/PostgreSQL/TencentDB API
    memory_context: str = ""        # Kontekst RAG pobrany w fetch_memory

    # =============================================================================
    # ROZUMOWANIE LLM
    # =============================================================================
    is_reasoning: bool = False      # Czy uruchamiać tryb myślowy? (system thinking)
    reason_response: str = ""       # Wynik myślenia agenta

    # =============================================================================
    # ROUTING (router -> route_next)
    # =============================================================================
    next: Optional[str] = None      # Wybrana gałąź: code_analysis|reasoning_node|text_processing
    model_role: Optional[str] = None  # code|reasoning|text

    # =============================================================================
    # NARZĘDZIA I ODPOWIEDZI
    # =============================================================================
    context_window_entries: List[dict] = []  # L3: Ostatnie Q&A dla RAG
    tool_responses: List[dict] = []         # Wyniki wywołania narzędzi (SQL, etc.)
    tool_summary: str = ""                 # Streszczenie wyników narzędzi
    final_response: str = ""              # Ostateczna odpowiedź dla użytkownika
    system_instructions: str = ""         # Systemowe instrukcje agenta
