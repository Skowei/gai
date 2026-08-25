#!/usr/bin/env python3
"""
==============================================================================
AI Ecosystem V2.0 - Flask Backend (orchestrator)
POST /api/chat                  -> routing modelu -> Ollama -> pamięć agenta
POST /api/v1/chat/completions   -> kompatybilność z Cline / OpenAI API
POST /agent-query               -> obsługa LangGraph
GET  /health                    -> status Ollamy i pamięci
==============================================================================
Plik samowystarczalny z automatyczną rejestracją agenta i obsługą pamięci TencentDB.
"""

import os
import re
import time
import logging

import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json

# -----------------------------------------------------------------------------
# KONFIGURACJA (z docker-compose / .env)
# -----------------------------------------------------------------------------

MEMORY_API_URL = os.environ.get("API_URL", "http://agent_memory:8420").rstrip("/")
MEMORY_API_KEY = os.environ.get("API_KEY", "test-team")
MEMORY_ADD_ENDPOINT = "/v2/conversation/add"

OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
).rstrip("/")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))

OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
MEMORY_FETCH_LIMIT = int(os.environ.get("MEMORY_FETCH_LIMIT", "30"))

CODE_MODEL = os.environ.get("CODE_MODEL", "qwen2.5-coder:7b")
REASONING_MODEL = os.environ.get("REASONING_MODEL", "qwen3.5:latest")
TEXT_MODEL = os.environ.get("TEXT_MODEL", "qwen3.5:latest")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen2.5vl")

CODE_TRIGGERS = (
    "python", "sql", "xml", "svg", "kod", "funkcja", "script", "json",
    "select", "show", "describe", "explain", "delete", "insert",
)
REASON_TRIGGERS = ("dlaczego", "oblicz", "matematyka", "logika", "rozwiąż", "porównaj")

SYSTEM_PROMPT = (
    "Jesteś pomocnym asystentem AI Ecosystem V2.0. Odpowiadaj po polsku, "
    "zwięźle i konkretnie. Jeśli w prompcie dostarczono 'Kontekst z pamięci', "
    "bezwzględnie wykorzystaj go do udzielenia odpowiedzi na pytania użytkownika o historię lub jego preferencje."
)

MEMORY_TEAM_ID = os.environ.get("DEFAULT_ISOLATION_ID", MEMORY_API_KEY)
MEMORY_USER_ID = os.environ.get("USER_ID", "default")

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("ai-ecosystem")

app = Flask(__name__)
CORS(app)
_session = requests.Session()

# -----------------------------------------------------------------------------
# AUTOMATYCZNE ZARZĄDZANIE AGENTEM
# -----------------------------------------------------------------------------

def _memory_headers():
    return {
        "Authorization": "Bearer local",
        "x-tdai-service-id": MEMORY_API_KEY,
        "Content-Type": "application/json",
    }


def ensure_agent_exists(agent_id: str):
    """Rejestruje agenta w usłudze pamięci, jeśli jeszcze nie istnieje."""
    try:
        _session.post(
            f"{MEMORY_API_URL}/v2/agent/create",
            json={
                "team_id": MEMORY_TEAM_ID,
                "agent_id": agent_id,
                "name": f"Agent {agent_id}",
            },
            headers=_memory_headers(),
            timeout=5,
        )
    except Exception as exc:
        log.warning("Błąd upewniania się o istnieniu agenta: %s", exc)


def get_agent_id() -> str:
    agent_id = os.environ.get("AGENT_ID", "agent_default")
    ensure_agent_exists(agent_id)
    return agent_id


# -----------------------------------------------------------------------------
# LANGGRAPH WORKFLOW IMPORT (z fallback)
# -----------------------------------------------------------------------------

try:
    from src.graph.state import AgentState
    from src.graph.nodes import (
        fetch_memory_node,
        router_node,
        route_next,
        code_analysis_node,
        reasoning_node,
        text_processing_node,
        execute_tools_node,
        generate_final_response_node,
    )
    _WORKFLOW_AVAILABLE = True
except ImportError:
    _WORKFLOW_AVAILABLE = False
    log.debug("LangGraph workflow unavailable - using fallback to ask_ollama()")


def build_graph():
    """Budowanie i kompilacja workflowu LangGraph (lub fallback do prostego przepływu)."""
    if not _WORKFLOW_AVAILABLE:
        from langgraph.graph import StateGraph, START, END

        class SimpleAgentState:
            messages: list
            memory_context: str = ""
            reason_response: str = ""
            next_node: str | None = None
            model_role: str | None = None
            context_window_entries: list = []
            tool_responses: list = []
            tool_summary: str = ""
            final_response: str = ""

        simple_state_cls = StateGraph(SimpleAgentState)

        def fallback_ask_node(state):
            return {
                "final_response": ask_ollama([{"role": "system", "content": SYSTEM_PROMPT}, *state["messages"]]),
                "memory_data": {},
                "context_window_entries": [],
                "tool_responses": [],
                "tool_summary": "",
                "model_role": None,
            }

        simple_state_cls.add_node("ask", fallback_ask_node)
        simple_state_cls.add_edge(START, "ask")
        return simple_state_cls.compile()
    else:
        from langgraph.graph import StateGraph, START, END
        graph_builder = StateGraph(AgentState)

        graph_builder.add_node("fetch_memory", fetch_memory_node)
        graph_builder.add_node("router", router_node)
        graph_builder.add_node("code_analysis", code_analysis_node)
        graph_builder.add_node("reasoning_node", reasoning_node)
        graph_builder.add_node("text_processing", text_processing_node)
        graph_builder.add_node("execute_tools", execute_tools_node)
        graph_builder.add_node("generate_final_response", generate_final_response_node)

        graph_builder.add_edge(START, "fetch_memory")
        graph_builder.add_edge("fetch_memory", "router")
        graph_builder.add_conditional_edges(
            "router",
            route_next,
            {
                "code_analysis": "code_analysis",
                "reasoning_node": "reasoning_node",
                "text_processing": "text_processing",
            },
        )

        for node_name in ("code_analysis", "reasoning_node", "text_processing"):
            graph_builder.add_edge(node_name, "execute_tools")

        graph_builder.add_edge("execute_tools", "generate_final_response")
        graph_builder.add_edge("generate_final_response", END)

        return graph_builder.compile()


# -----------------------------------------------------------------------------
# HELPERY
# -----------------------------------------------------------------------------

def pick_model(query: str) -> str:
    """Routing zapytania do właściwego modelu (kod / logika / tekst)."""
    lower = query.lower()
    if any(t in lower for t in CODE_TRIGGERS):
        return CODE_MODEL
    if any(t in lower for t in REASON_TRIGGERS):
        return REASONING_MODEL
    return TEXT_MODEL


def ollama_available(timeout: int = 5) -> bool:
    try:
        r = _session.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _memory_available() -> bool:
    try:
        return _session.get(f"{MEMORY_API_URL}/health", timeout=3).status_code < 500
    except Exception:
        return False


def ask_ollama(history: list, model: str = None) -> str:
    """Wywołanie API Ollamy w formacie zgodnym z OpenAI lub natywnym, bez bloków <think>."""
    base_url = OLLAMA_BASE_URL
    if base_url.endswith("/v1"):
        endpoint = f"{base_url}/chat/completions"
    else:
        endpoint = f"{base_url}/api/chat"

    # Jeśli model został przekazany jawnie z endpointu Cline, używamy go.
    # W przeciwnym wypadku odpalamy stary mechanizm pick_model.
    final_model = model if model else pick_model(history[-1]["content"] if history else "")

    messages_payload = history if model else [{"role": "system", "content": SYSTEM_PROMPT}, *history]

    payload = {
        "model": final_model,
        "messages": messages_payload,
        "stream": False,
        "options": {"num_ctx": OLLAMA_NUM_CTX}
    }
    
    r = _session.post(endpoint, json=payload, timeout=OLLAMA_TIMEOUT)
    r.raise_for_status()
    resp_json = r.json()
    
    content = ""
    
    # 1. Przechwytujemy natywny format Ollamy (/api/chat) -> dla Cline
    if "message" in resp_json and isinstance(resp_json["message"], dict):
        content = resp_json["message"].get("content", "")
        
    # 2. Przechwytujemy format OpenAI (/v1/chat/completions) -> dla Postmana (BEZPIECZNIE, bez .get na liście)
    elif "choices" in resp_json and isinstance(resp_json["choices"], list) and resp_json["choices"]:
        first_choice = resp_json["choices"][0]
        if isinstance(first_choice, dict):
            content = first_choice.get("message", {}).get("content", "")

    # ZABEZPIECZENIE: Zapisujemy surowy tekst z Ollamy
    content_str = str(content).strip()
    if not content_str:
        return "Model zwrócił pustą odpowiedź. Spróbuj ponownie."

    # Bezpieczne wycinanie bloku myślenia <think>... </think>
    if "<think>" in content_str:
        if "</think>" in content_str:
            cleaned_content = re.sub(r"<think>.*?</think>", "", content_str, flags=re.DOTALL).strip()
        else:
            # Sytuacja awaryjna: model nie zdążył domknąć tagu, ucinamy tylko część myślową
            cleaned_content = content_str.split("<think>")[0].strip()
    else:
        cleaned_content = content_str

    # --- OSTATECZNY BEZPIECZNIK ---
    if not cleaned_content:
        log.warning("Wyrażenie regularne wycięło całą odpowiedź. Przywracam surowy tekst.")
        return content_str

    return cleaned_content


def fetch_memory_context(session_id: str, query: str = "") -> str:
    """Pobiera i poprawnie formatuje kontekst historii z TencentDB."""
    agent_id = get_agent_id()
    try:
        payload = {
            "team_id": MEMORY_TEAM_ID,
            "agent_id": agent_id,
            "user_id": MEMORY_USER_ID,
            "session_id": session_id,
            "query": query,
            "limit": MEMORY_FETCH_LIMIT,
        }
        r = _session.post(
            f"{MEMORY_API_URL}/v2/conversation/query",
            json=payload,
            headers=_memory_headers(),
            timeout=5,
        )
        if r.status_code != 200:
            log.warning("Memory fetch failed [%s]: %s", r.status_code, r.text)
            return ""

        res_json = r.json()
        messages = res_json.get("data", {}).get("messages", []) or res_json.get("items", [])
        if not messages:
            return ""

        parts = []
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            
            role = msg.get("role", "unknown")
            content = msg.get("text") or msg.get("content") or msg.get("message")
            if isinstance(content, dict):
                content = content.get("content", "")
                
            if content:
                display_role = "Użytkownik" if role == "user" else "Asystent"
                parts.append(f"{display_role}: {str(content).strip()}")

        context_str = "\n".join(parts)
        if context_str:
            log.info(f"Pomyślnie zmapowano kontekst z {len(messages)} wiadomości dla sesji {session_id}")
        return context_str

    except Exception as exc:
        log.error("Błąd podczas przetwarzania wiadomości z TencentDB: %s", exc)
        return ""


def store_conversation(session_id: str, user_query: str, assistant_answer: str) -> None:
    """Best-effort zapis rozmowy w pamięci agenta (L1/L2)."""
    messages = [
        {"role": "user", "content": user_query},
        {"role": "assistant", "content": assistant_answer},
    ]
    try:
        r = _session.post(
            f"{MEMORY_API_URL}{MEMORY_ADD_ENDPOINT}",
            json={
                "team_id": MEMORY_TEAM_ID,
                "agent_id": get_agent_id(),
                "user_id": MEMORY_USER_ID,
                "session_id": session_id,
                "messages": messages,
            },
            headers=_memory_headers(),
            timeout=15,
        )
        result = r.json()
        ok = result.get("code") == 0 or r.status_code == 200
        log.info("Memory store %s", "OK" if ok else f"FAILED: {result}")
    except Exception as exc:
        log.warning("Memory store unavailable: %s", exc)


# -----------------------------------------------------------------------------
# ENDPOINTY
# -----------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "ollama": ollama_available(),
        "memory": _memory_available(),
        "models": {
            "code": CODE_MODEL,
            "reasoning": REASONING_MODEL,
            "text": TEXT_MODEL,
            "vision": VISION_MODEL,
        },
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify({
                "success": False,
                "error": "Pole 'query' jest wymagane",
            }), 400

        session_id = data.get("session_id") or f"sess-{int(time.time() * 1000)}"

        if not ollama_available():
            return jsonify({
                "success": False,
                "error": f"Ollama niedostępna pod {OLLAMA_BASE_URL}",
            }), 503

        context = fetch_memory_context(session_id, query)

        history = []
        if context:
            history.append({
                "role": "system",
                "content": f"Oto dotychczasowa historia rozmowy i fakty z pamięci:\n{context}"
            })
        history.append({"role": "user", "content": query})

        answer = ask_ollama(history)
        store_conversation(session_id, query, answer)

        return jsonify({
            "success": True,
            "response": answer,
            "model": pick_model(query),
            "session_id": session_id,
            "memory_context_used": bool(context),
        })

    except requests.Timeout:
        return jsonify({"success": False, "error": "Timeout Ollamy"}), 504
    except Exception as exc:
        log.exception("chat failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/chat/completions", methods=["POST"])
@app.route("/api/v1/chat/completions", methods=["POST"])
def cline_chat_completions():
    try:
        data = request.get_json(force=True, silent=True) or {}
        messages = data.get("messages", [])
        if not messages or not isinstance(messages, list):
            return jsonify({"error": "Brak poprawnej tablicy 'messages'"}), 400
            
        last_message = messages[-1] if messages else {}
        query = last_message.get("content", "").strip() or "Cześć"
        session_id = request.headers.get("X-Session-Id") or "cline-session-ai"

        if not ollama_available():
            return jsonify({"error": f"Ollama niedostępna pod {OLLAMA_BASE_URL}"}), 503

        context = fetch_memory_context(session_id, query)

        history_for_ollama = []
        if context:
            history_for_ollama.append({
                "role": "system",
                "content": f"[Kontekst z pamięci długoterminowej użytkownika]:\n{context}"
            })
            
        for msg in messages:
            if isinstance(msg, dict) and msg.get("content"):
                history_for_ollama.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

        chosen_model = pick_model(query)
        answer = ask_ollama(history_for_ollama, model=chosen_model)

        if not answer:
            answer = "Nie udało się wygenerować odpowiedzi. Spróbuj powtórzyć zapytanie."

        store_conversation(session_id, query, answer)

        # ---> ROZWIĄZANIE DLA CLINE: GENEROWANIE STRUMIENIA KOMPATYBILNEGO Z OPENAI <---
        def generate_chunks():
            chunk_id = f"chatcmpl-{int(time.time())}"
            created_time = int(time.time())
            
            # Krok 1: Wyślij blok tekstu jako pojedynczy, duży "delta chunk"
            chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": chosen_model,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": answer
                    },
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            
            # Krok 2: Wyślij sygnał zakończenia strumienia (finish_reason: stop)
            final_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": chosen_model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            
            # Krok 3: Wyślij oficjalny token zamknięcia protokołu OpenAI
            yield "data: [DONE]\n\n"

        # Zwracamy obiekt Response z odpowiednim nagłówkiem text/event-stream
        return Response(generate_chunks(), mimetype="text/event-stream")

    except requests.Timeout:
        return jsonify({"error": "Timeout Ollamy"}), 504
    except Exception as exc:
        log.exception("cline chat completions failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/v1/models", methods=["GET"])
@app.route("/api/models", methods=["GET"])
def cline_models_discovery():
    """Pozwala wtyczce Cline na automatyczne wykrycie pełnej listy Twoich modeli ról AI."""
    return jsonify({
        "object": "list",
        "data": [
            {"id": TEXT_MODEL, "object": "model", "created": int(time.time()), "owned_by": "ollama"},
            {"id": CODE_MODEL, "object": "model", "created": int(time.time()), "owned_by": "ollama"},
            {"id": REASONING_MODEL, "object": "model", "created": int(time.time()), "owned_by": "ollama"},
            {"id": VISION_MODEL, "object": "model", "created": int(time.time()), "owned_by": "ollama"}
        ]
    })


@app.route("/agent-query", methods=["POST"])
def agent_query():
    try:
        data = request.get_json(force=True, silent=True) or {}
        messages = data.get("messages", [])

        if not messages:
            return jsonify({
                "success": False,
                "error": "Pole 'messages' (lista obiektów {role, content}) jest wymagana",
            }), 400

        user_query = messages[-1].get("content", "").strip() if messages else ""
        session_id = data.get("session_id") or messages[0].get("session_id") or f"sess-{int(time.time() * 1000)}"

        context = fetch_memory_context(session_id, user_query)

        initial_state = {
            "messages": messages,
            "session_id": session_id,
            "memory_context": context,
            "reason_response": "",
            "next_node": None,
            "model_role": None,
            "context_window_entries": [],
            "tool_responses": [],
            "tool_summary": "",
            "final_response": "",
        }

        graph = build_graph()
        result = graph.invoke(initial_state)

        final_response = result.get("final_response", "")

        if user_query and final_response:
            store_conversation(session_id, user_query, final_response)

        return jsonify({
            "success": True,
            "final_response": final_response,
            "memory_data": result.get("memory_data", {"context_used": context}),
            "model_role": result.get("model_role", "text"),
            "tool_responses": result.get("tool_responses", []),
        })

    except requests.Timeout:
        return jsonify({"success": False, "error": "Timeout agenta"}), 504
    except Exception as exc:
        log.exception("agent_query failed")
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))