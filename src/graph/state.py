"""
=============================================================================
AI Ecosystem V2.0 - LangGraph State
Stan workflowu agenta AI (memory -> reasoning -> tools -> response)
=============================================================================
"""

from typing import TypedDict, List, Annotated, Optional
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Stan workflowu agenta AI z rozszerzeniami o pamięć i narzędzia."""

    # =============================================================================
    # PAMIĘĆ AGENTA (L0-L3 z MemoryClient)
    # =============================================================================
    memory_data: dict = {}  # Dane z Redis/PostgreSQL/TencentDB API

    # =============================================================================
    # ROZUMOWANIE LLM
    # =============================================================================
    is_reasoning: bool = False  # Czy uruchamiać tryb myślowy? (system thinking)
    reason_response: str = ""   # Wynik myślenia agenta

    # =============================================================================
    # NARZĘDZIA I ODPowiedzi
    # =============================================================================
    context_window_entries: List[dict] = []  # L3: Ostatnie Q&A dla RAG
    tool_responses: List[dict] = []         # Wyniki wywołania narzędzi (SQL, etc.)
    final_response: str = ""                 # Ostateczna odpowiedź dla użytkownika
