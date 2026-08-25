"""
==============================================================================
AI Ecosystem V2.0 - LangGraph Nodes
Węzły workflowu: memoria, routing, kod, logika, tekst, narzędzi, odpowiedź.
Każdof węzeł woła prawdziwą modelia Ollama via src.llm.
==============================================================================
"""

import os
import sys
from typing import Any, Optional

sys.path.insert(0, "/home/maciei/dev/ai")

from src.llm import (
    ollama_chat,
    route_model,
    route_role,
    CODE_MODEL,
    REASONING_MODEL,
    TEXT_MODEL,
    is_healthy,
)

# =============================================================================
# HELPERS
# =============================================================================

def _last_user_message(state) -> str:
    """Wyciąga ostatnią wiadomość użytkownika z stanu (dict lub Message)."""
    messages = state.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return str(last.get("content", ""))
    return str(getattr(last, "content", "") or "")


def _llm_system(model_role: str) -> str:
    """Systemowe instrukcje dla danego modelu."""
    prompts = {
        "code": (
            "Jesteś ekspertem do analizy kodu i SQL. Pisz TYLKO poprawny, "
            "bezpieczny kod. Do zapytań SQL używaj TYLKO SELECT (read-only!)."
        ),
        "reasoning": (
            "Jesteśe asystent do myślenia logicznego, matematiki i analizy. "
            "Odpowiadaj krokowo i dokładnie."
        ),
        "text": (
            "Jesteś pomocnym asystentem tekstu. Odpowiadaj po polsku, zwięźle "
            "i konkretnie."
        ),
    }
    return prompts.get(model_role, prompts["text"])


def _ask(model_name: str, role: str, user_message: str) -> str:
    """Wywołanie Ollama z system prompt + historii z stanu grafu."""
    if not is_healthy():
        return f"[OFFLINE] Ollama niedostępna - model {model_name}"
    try:
        return ollama_chat(
            [{"role": "system", "content": _llm_system(role)},
             {"role": "user", "content": user_message}],
            model=model_name,
        )
    except Exception as exc:
        return f"[BŁĄD modelu {model_name}] {exc}"


# Aliasy dla spójneści z resztem kodu:
_syscall = _ask
_last_message = _last_user_message


# =============================================================================
# WĘZŁY
# =============================================================================

def fetch_memory_node(state, config: Any = None) -> dict:
    """L0-L3: Systemowe instrukcja + kontekst pamięci (best-effort)."""
    user_message = _last_message(state)

    system_instructions = (
        "Jesteś asystentem AI wspieranym przez bazę pamięci (L0-L3). "
        "Użyj dostępnych narzędzi do analizy kodu, SQL, tekstu i obrazów."
    )

    memory_context = ""
    try:
        from src.memory.client import get_memory_client
        memory_context = get_memory_client().build_context(user_message, top_k=3)
    except Exception as exc:
        memory_context = f"# (pamięć niedostępna: {exc})"

    return {
        "messages": [{"role": "assistant",
                      "content": "[MEMORY] Pobrono kontekst pamięci."}],
        "system_instructions": system_instructions,
        "memory_context": memory_context or "",
    }


def router_node(state: dict, config: Any = None) -> dict:
    """Wybieraj gałąź: kod / logika / tekst wedle treści zapytania."""
    user_message = _last_message(state)
    role = route_role(user_message)
    if role == "code":
        return {"next": "code_analysis", "model_role": "code"}
    if role == "reasoning":
        return {"next": "reasoning_node", "model_role": "reasoning"}
    return {"next": "text_processing", "model_role": "text"}


def route_next(state: dict) -> str:
    """Funkcja krawędzi: na każdodf powrót daje kierunek gałązi."""
    return state.get("next", "text_processing")


def code_analysis_node(state: dict, config: Any = None) -> dict:
    """Kod/SQL/XML/SVG - qwen2.5-coder."""
    user_message = _last_message(state)
    response = _syscall(CODE_MODEL, "code", user_message)
    return {"messages": [{"role": "assistant", "content": response}]}


def reasoning_node(state: dict, config: Any = None) -> dict:
    """Logika/matematyka - deepseek/qwen rozumujący."""
    user_message = _last_message(state)
    response = _syscall(REASONING_MODEL, "reasoning", user_message)
    return {"messages": [{"role": "assistant", "content": response}]}


def text_processing_node(state: dict, config: Any = None) -> dict:
    """Tekst/Obsidian/PL - llama3.1/qwen3.5."""
    user_message = _last_message(state)
    response = _syscall(TEXT_MODEL, "text", user_message)
    return {"messages": [{"role": "assistant", "content": response}]}
def execute_tools_node(state: dict, config: Any = None) -> dict:
    """Wykonywanie narzędzi SQL (read-only z guardrails) i Obsidian."""
    user_message = _last_message(state)
    tool_results = []
    tool_msg_parts = []
    lower = user_message.lower()

    # 1) SQL tool - tylko gdy zapytanie wygląda na SQL (SELECT/DESCRIBE...)
    if any(k in lower for k in ("select ", "show ", "describe ", "explain ", "sql")):
        # Bezpieczna pgvector/select -> guardrails filtruje
        from src.tools.sql_tool import execute_sql
        # Wyciągnij linię z SELECT... (jeśli wklejono całe zapytanie)
        import re as _re
        match = _re.search(
            r"SELECT\b.*?(?:;|$)", user_message,
            _re.IGNORECASE | _re.DOTALL
        )
        candidate = match.group(0).strip() if match else None
        if candidate:
            try:
                result = execute_sql(candidate)
                tool_results.append({
                    "tool": "sql",
                    "query": candidate,
                    "success": result.get("success", False),
                    "message": result.get("message", ""),
                    "rows": result.get("rows", [])[:10],
                })
                tool_msg_parts.append(
                    f"[SQL] {candidate}\n[baza] {result.get('message', '')}"
                    + (f"\n{result['rows']}" if result.get("rows") else "")
                )
            except Exception as exc:
                tool_msg_parts.append(f"[SQL] Błąd wykonania: {exc}")

    # 2) Obsidian - jeżeli prośba o notatki / pamięć
    if any(k in lower for k in ("notatka", "obsidian", "pokaż notatki", "szukaj")):
        from src.tools.obsidian_tool import search_notes
        try:
            notes = search_notes(user_message, top_k=3)
            tool_results.append({"tool": "obsidian", "results": notes})
            tool_msg_parts.append(f"[OBSIDIAN] {len(notes)} pasujących notatek")
        except Exception as exc:
            tool_msg_parts.append(f"[OBSIDIAN] Błąd: {exc}")

    if tool_results:
        return {
            "messages": [{
                "role": "assistant",
                "content": "[TOOLS] Wykonano " + str(len(tool_results)) + " narzędzi.",
            }],
            "tool_responses": tool_results,
            "tool_summary": "\n".join(tool_msg_parts),
        }
    return {"tool_responses": [], "tool_summary": ""}


def generate_final_response_node(state: dict, config: Any = None) -> dict:
    """Final finalnej odpowiedzi dla użytkownika (ostatni węzeł grafu)."""
    user_message = _last_message(state)
    assistant_parts = [
        m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
        for m in (state.get("messages") or [])
        if (isinstance(m, dict) and m.get("role") == "assistant")
    ]
    model_block = "\n".join(p for p in assistant_parts if p)

    tool_summary = state.get("tool_summary", "") or ""

    final = _ask(
        TEXT_MODEL,
        "text",
        f"""Jesteś precyzyjnym asystentem. Twoim zadaniem jest udzielenie odpowiedzi użytkownikowi na podstawie DOSTARCZONYCH WYNIKÓW NARZĘDZI.
ZASADA KRYSTALICZNĄ: Jeśli w sekcji "Wyniki narzędzi" znajdują się dane (np. z Obsidiana), MUSISZ oprzeć swoją odpowiedź WYŁĄCZNIE NA NICH. Całkowicie zignoruj wszelkie wcześniejsze konfabulacje, pamięci podręczne czy domysły. Jeśli wyniki zawierają treść notatki, po prostu ją przedstaw.

Model wnioski:
{model_block}

Wyniki narzędzi:
{tool_summary or "(brak)"}

Oryginalne pytanie:
{user_message}""",
    )
    return {"final_response": final}