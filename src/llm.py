#!/usr/bin/env python3
"""
==============================================================================
AI Ecosystem V2.0 - Wspólny klient Ollama
Jedno miejsce dla wywołań LLM: routing modeli, chat, embeddings.
==============================================================================
"""

import os
import re
from typing import Any, Dict, List, Optional

import requests

# =============================================================================
# KONFIGURACJA (zmienne środowiskowe z .env / docker-compose)
# =============================================================================

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

# Mapowanie ról na modele (zgodnie z .env.example)
CODE_MODEL = os.getenv("CODE_MODEL", "qwen2.5-coder:7b")
REASONING_MODEL = os.getenv("REASONING_MODEL", "qwen3.5:latest")
TEXT_MODEL = os.getenv("TEXT_MODEL", "qwen3.5:latest")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen3.5:latest")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")

_SESSION = requests.Session()

# Słowa-wyzwalacze routingu (spójne z src/graph/nodes.py)
_CODE_TRIGGERS = (
    "python", "sql", "xml", "svg", "kod", "funkcja", "script", "json",
    "select", "show", "describe", "explain", "delete", "insert",
    "update ", "drop ", "create table", "from ", "where ",
)
_REASON_TRIGGERS = ("dlaczego", "oblicz", "matematyka", "logika", "rozwiąż", "porównaj")


def route_model(text: str, force_reasoning: bool = False) -> str:
    """Wybiera model według treści zapytania (router jak w LangGraph)."""
    role = route_role(text, force_reasoning=force_reasoning)
    return {
        "code": CODE_MODEL,
        "reasoning": REASONING_MODEL,
        "text": TEXT_MODEL,
    }[role]


def route_role(text: str, force_reasoning: bool = False) -> str:
    """Zwraca rolę ('code' | 'reasoning' | 'text') dla zapytania."""
    if force_reasoning:
        return "reasoning"
    lower = text.lower()
    if any(t in lower for t in _CODE_TRIGGERS):
        return "code"
    if any(t in lower for t in _REASON_TRIGGERS):
        return "reasoning"
    return "text"


def strip_think(response: str) -> str:
    """Usuwa bloki <think>...</think> z odpowiedzi modeli rozumujących."""
    return re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()


def ollama_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    stream: bool = False,
) -> str:
    """
    Wywołanie /api/chat w Ollama (non-streaming domyślnie).

    Args:
        messages: Lista {"role": ..., "content": ...}
        model: Nazwa modelu (domyślnie routing wg treści)
        stream: Jeśli True, zwraca generator kawałków tekstu.

    Returns:
        str: Treść odpowiedzi asystenta (bez bloków <think>).
    """
    if model is None:
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        model = route_model(last_user)

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"num_ctx": OLLAMA_NUM_CTX},
    }
    response = _SESSION.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=OLLAMA_TIMEOUT,
        stream=stream,
    )
    response.raise_for_status()

    if stream:
        def _generate():
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = line.json()
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if chunk.get("done"):
                    break
        return "".join(_generate()) if False else _generate()  # stream zwraca generator

    data = response.json()
    content = data.get("message", {}).get("content", "")
    return strip_think(content)


def ollama_generate(prompt: str, model: Optional[str] = None) -> str:
    """Proste uzupełnienie /api/generate (jeden prompt -> jedna odpowiedź)."""
    if model is None:
        model = route_model(prompt)
    response = _SESSION.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    return strip_think(response.json().get("response", ""))


def fallback_embedding(text: str, dim: int = 1024) -> List[float]:
    """
    Deterministyczny wektor zastępczy (bez modelu embeddingu).

    Używany tylko wtedy, gdy Ollama nie ma modelu embeddingowego (bge-m3).
    Takie same/sąsiednie tokeny dają zbliżone wektory — "współdzielony hash".
    Zainstaluj model:  ollama pull bge-m3  → wtedy używane są prawdziwe
    embeddings semantyczne.
    """
    import hashlib

    vec = [0.0] * dim
    words = re.findall(r"[\w]+", text.lower())[:256]
    if not words:
        words = ["<empty>"]
    for w in words:
        h = hashlib.sha256(w.encode("utf-8")).digest()
        # rzuć 4 hasła na zakres [-1,1]
        for i in range(min(4, len(h))):
            idx = (h[i] * 255) % dim
            sign = 1.0 if h[i] % 2 == 0 else -1.0
            vec[idx] += sign * (h[i] / 255.0)
    norm = max(1e-9, (sum(v * v for v in vec) ** 0.5))
    return [v / norm for v in vec]


def ollama_embeddings(text: str, model: Optional[str] = None) -> Optional[List[float]]:
    """Embeddings przez /api/embed (Ollama >= 0.3) z fallbackiem na /api/embeddings."""
    model = model or EMBEDDING_MODEL
    try:
        response = _SESSION.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": model, "input": text},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(data["error"])
        embeddings = data.get("embeddings", [])
        if embeddings and isinstance(embeddings[0], list):
            return embeddings[0]
    except Exception:
        pass
    # Fallback: starszy endpoint
    try:
        response = _SESSION.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30,
        )
        response.raise_for_status()
        emb = response.json().get("embedding")
        if emb:
            return emb
    except Exception:
        pass
    # Ostateczny fallback: deterministyczny pseudovektor (gdy model nie istnieje)
    return fallback_embedding(text)


def is_healthy(timeout: int = 5) -> bool:
    """Sprawdzenie czy Ollama odpowiada."""
    try:
        response = _SESSION.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    print(f"Ollama: {OLLAMA_BASE_URL}")
    print(f"Dostępny: {is_healthy()}")
    if is_healthy():
        models = _SESSION.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10).json()
        names = [m["name"] for m in models.get("models", [])]
        print(f"Modele: {names}")
        answer = ollama_chat([{"role": "user", "content": "Powiedz krótko: test OK?"}])
        print(f"Test chat: {answer[:200]}")