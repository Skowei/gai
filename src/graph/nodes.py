
"""AI Ecosystem V2.0 - LangGraph Nodes
Węzły workflowu: router, code, reasoning, text
"""

from langgraph.graph import MessagesState, END
import psycopg2
import redis
from typing import Literal, Any


def route_to_code_analysis(state: MessagesState) -> dict:
    """Routing do analizy kodu/SQL/XML/SVG (qwen2.5-coder)."""
    triggers = ["python", "sql", "xml", "svg"]
    
    # Handle both HumanMessage/AIMessage objects and plain dicts
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    if isinstance(last_message, dict):
        content_lower = last_message.get("content", "").lower()
    else:
        content_lower = getattr(last_message, "content", "") or ""
    
    is_code_related = any(t in content_lower for t in triggers)
    if is_code_related or state.get("is_reasoning"):
        return {"next": "code_analysis"}
    return {"next": "reasoning_node"}


def route_to_reasoning(state: MessagesState) -> dict:
    """Routing do myślenia/logiki (deepseek-r1)."""
    return {"next": "reasoning_node"}


def route_to_text_handling(state: MessagesState) -> dict:
    """Routing do obsługi tekstu/notatek (llama3.1/PL)."""
    return {"next": "text_processing_node"}


def code_analysis_node(state: MessagesState, config: Any = None) -> dict:
    """Analiza kodu/SQL/XML/SVG — qwen2.5-coder"""
    
    # Handle both HumanMessage/AIMessage objects and plain dicts
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    if isinstance(last_message, dict):
        user_message = last_message.get("content", "")
    else:
        user_message = getattr(last_message, "content", "") or ""
    
    system_prompt = f"Ty jesteś ekspertem do analizy kodu i SQL.\nPisz TYLKO SELECT (read-only!).\nUser: {user_message}"
    assistant_response = f"[CODE MODEL] Analiza kodu/SQL dla: {user_message[:50]}..."
    return {"messages": [{"role": "assistant", "content": assistant_response}]}


def reasoning_node(state: MessagesState, config: Any = None) -> dict:
    """Myślenie/logika/matematyka — deepseek-r1"""
    
    # Handle both HumanMessage/AIMessage objects and plain dicts
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    if isinstance(last_message, dict):
        user_message = last_message.get("content", "")
    else:
        user_message = getattr(last_message, "content", "") or ""
    
    system_prompt = f"Ty jesteś asystentem do myślenia logicznego.\nZadanie: {user_message}"
    reasoning_response = f"[REASONING MODEL] Myślenie dla: {user_message[:50]}..."
    return {"messages": [{"role": "assistant", "content": reasoning_response}]}


def text_processing_node(state: MessagesState, config: Any = None) -> dict:
    """Przetwarzanie tekstu/notatek Obsidian — llama3.1"""
    
    # Handle both HumanMessage/AIMessage objects and plain dicts
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    if isinstance(last_message, dict):
        user_message = last_message.get("content", "")
    else:
        user_message = getattr(last_message, "content", "") or ""
    
    system_prompt = f"Ty jesteś asystentem do obsługi tekstu.\nZadanie: {user_message}"
    text_response = f"[TEXT MODEL] Przetwarzanie tekstu dla: {user_message[:50]}..."
    return {"messages": [{"role": "assistant", "content": text_response}]}


def vision_processing_node(state: MessagesState, config: Any = None) -> dict:
    """Przetwarzanie obrazów/SVG — qwen2-vl"""
    
    # Handle both HumanMessage/AIMessage objects and plain dicts
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    if isinstance(last_message, dict):
        user_message = last_message.get("content", "")
    else:
        user_message = getattr(last_message, "content", "") or ""
    
    vision_response = f"[VISION MODEL] Analiza wizualna dla: {user_message[:50]}..."
    return {"messages": [{"role": "assistant", "content": vision_response}]}


def fetch_memory_node(state: MessagesState, config: Any = None) -> dict:
    """Pobieranie danych pamięci z MemoryClient (RAG + system instructions)."""
    from langchain_core.runnables import ConfigurableField

    # Handle both HumanMessage/AIMessage objects and plain dicts
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    if isinstance(last_message, dict):
        user_message = last_message.get("content", "")
    else:
        user_message = getattr(last_message, "content", "") or ""
    
    # Pobieranie instrukcji systemu i kontekstu z bazy danych pamięci
    system_instructions = "Jesteś asystentem AI wspieranym przez bazę pamięci. Użyj dostępnych narzędzi do analizy kodu, SQL, tekstu i obrazów."
    
    response = f"[MEMORY FETCH] Systemowe instrukcje pobrane. Kontekst RAG: {user_message[:50]}..."
    return {"messages": [{"role": "assistant", "content": response}], "system_instructions": system_instructions}


def execute_tools_node(state: MessagesState, config: Any = None) -> dict:
    """Wywoływanie narzędzi SQL (z guardrails)."""
    import re
    
    # Handle both HumanMessage/AIMessage objects and plain dicts
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    if isinstance(last_message, dict):
        user_message = last_message.get("content", "")
    else:
        user_message = getattr(last_message, "content", "") or ""
    
    # Analiza czy użytkownik prosi o wykonanie zapytania SQL
    if any(keyword in user_message.lower() for keyword in ["select", "show", "describe", "query", "dostan", "pokaż"]):
        # Generowanie bezpiecznego SELECT (read-only!)
        sql_query = f"SELECT * FROM table WHERE condition = 'test'"  # Przykładowe zapytanie
        
        response = f"[SQL TOOL] Wygenerowano zapytanie: {sql_query[:100]}..."
        
        return {
            "messages": [{"role": "assistant", "content": response}],
            "tool_responses": [sql_query]  # Przekazanie narzędzia do wykonania
        }
    
