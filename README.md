# 🤖 AI Ecosystem V3.0 — 100% Lokalny System AI

**Backend:** FastAPI + LangGraph + Ollama (lokalne LLM)

## 📋 Spis Treści

- [🏗️ Architektura](#-architektura)
- [🔧 Instalacja i Uruchomienie](#-instalacja-i-uruchomienie)
- [🎯 API Endpoints](#-api-endpoints)
- [📦 Warstwy Pamięci](#-warstwy-pamięci)
- [🔒 Bezpieczeństwo](#-bezpieczeństwo)
- [⚙️ Konfiguracja](#-konfiguracja)

---

## 🏗️ Architektura

```
┌────────────────────────────────────────────────────────────────┐
│                    AI Ecosystem V3.0                           │
├────────────────────────────────────────────────────────────────┤
│  Interfejsy:    FastAPI REST · WebSocket · Cline Compatibility │
│                           │                                    │
│                           ▼                                    │
│  LangGraph Workflow (app/core/agent/)                          │
│  START → fetch_memory → cognitive_core → [tools | finalize]   │
│                           │                                    │
│  Modele (Ollama):                                             │
│    • code_analysis  ─► qwen2.5-coder:7b     (kod, SQL)       │
│    • reasoning      ─► deepseek-r1:8b       (logika)         │
│    • text           ─► llama3.1:8b          (konwersacje)    │
│    • vision         ─► llama3.2-vision:11b  (obrazy)         │
│    • embedding      ─► mxbai-embed-large    (pgvector)       │
│                           │                                    │
│                           ▼                                    │
│  Warstwy Pamięci:                                             │
│    • L1 Redis         — krótkoterminowy cache sesji           │
│    • L2 PostgreSQL    — wektory embeddings (pgvector)         │
│    • L3 Local Notes   — wewnętrzny cache agenta               │
│    • L4 Obsidian Vault — dokumenty użytkownika                │
├────────────────────────────────────────────────────────────────┤
│  Narzędzia:                                                    │
│    • sql_tool.py        → PostgreSQL (read-only)               │
│    • obsidian_tool.py   → Vault Markdown → pgvector            │
│    • guardrails.py      → blokuje INSERT/UPDATE/DELETE/DROP    │
└────────────────────────────────────────────────────────────────┘
```

### Struktura Projektu

```
app/
├── api/routes/
│   ├── chat.py          # REST endpoint /api/v1/chat
│   └── cline.py         # Cline/OpenAI compatible API
├── core/
│   ├── agent/
│   │   ├── brain.py     # LangGraph workflow definition
│   │   ├── state.py     # AgentState (Pydantic)
│   │   └── nodes/       # Węzły grafu
│   │       ├── fetch.py      # Pobieranie pamięci L1-L4
│   │       ├── cognitive.py  # Decyzja LLM co robić
│   │       ├── tools.py      # Wykonanie narzędzi
│   │       ├── finalize.py   # Synteza odpowiedzi
│   │       └── utils.py      # Współdzielone funkcje
│   ├── config.py        # Konfiguracja systemu
│   ├── llm_factory.py   # Fabryka modeli Ollama
│   └── memory/
│       ├── postgres.py  # UnifiedMemoryManager (L2/L3/L4)
│       └── indexer.py   # Skanowanie Obsidian vault
├── security/
│   └── guardrails.py    # Walidacja SQL (read-only)
└── tools/mcp_system/
    ├── sql_tool.py      # Asynchroniczne narzędzie SQL
    └── obsidian_tool.py # Asynchroniczny dostęp do Vault
```

## 🔧 Instalacja i Uruchomienie

### Wymagania
- Docker + Docker Compose
- Ollama (lokalna lub w kontenerze)

### Uruchomienie z Docker:

```bash
# 1. Skopiuj konfigurację
cp .env.example .env

# 2. Edytuj .env - ustaw hasło do bazy
POSTGRES_PASSWORD=twoje_bezpieczne_haslo

# 3. Uruchom wszystkie usługi
make up

# 4. Sprawdź status
make check
```

### Uruchomienie lokalne (bez Docker):

```bash
# 1. Zainstaluj zależności
pip install -r requirements.txt

# 2. Upewnij się, że Ollama działa i posiada modele
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
ollama pull deepseek-r1:8b
ollama pull llama3.1:8b-instruct-q4_K_M
ollama pull mxbai-embed-large:latest

# 3. Uruchom serwer
python main.py
```

Serwer dostępny na `http://localhost:8000`

## 🎯 API Endpoints

### Chat (Vue 3 / Postman)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Cześć!", "session_id": "moja_sesja"}'
```

### Cline / OpenAI Compatible

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [{"role": "user", "content": "Cześć!"}],
    "stream": true
  }'
```

### Lista endpointów

| Endpoint | Metoda | Opis |
|----------|--------|------|
| `/api/v1/chat` | POST | Główny endpoint czatu |
| `/api/v1/chat/completions` | POST | Cline/OpenAI API |
| `/api/v1/models` | GET | Lista dostępnych modeli |
| `/ws/v1/stream` | WebSocket | Strumieniowanie w czasie rzeczywistym |

## 📦 Warstwy Pamięci

| Warstwa | Technologia | Opis |
|---------|-------------|------|
| **L1** | Redis | Cache sesji (TTL 2h), szybki dostęp do historii |
| **L2** | PostgreSQL + pgvector | Semantyczne wyszukiwanie embeddings |
| **L3** | Local Files | Wewnętrzne notatki agenta (/app/local_notes) |
| **L4** | Obsidian Vault | Dokumenty użytkownika (/app/obsidian_vault) |

## 🔒 Bezpieczeństwo

- **SQL Guardrails**: `guardrails.py` blokuje INSERT/UPDATE/DELETE/DROP - agent może tylko SELECT/SHOW/DESCRIBE/EXPLAIN
- **Asynchroniczność**: Wszystkie operacje I/O są nieblokujące
- **CORS**: Konfigurowalne origins (domyślnie otwarte dla dev)

## ⚙️ Konfiguracja

Plik `.env`:

```env
POSTGRES_USER=agent
POSTGRES_PASSWORD=twoje_bezpieczne_haslo
POSTGRES_DB=ai_memory
REDIS_URL=redis://redis:6379/0
```

Plik `config/models.yaml`:
- Modele LLM z parametrami (temperature, num_ctx, itp.)
- Role modeli (code_analysis, reasoning, text, vision, embedding)
- Ustawienia Ollama (timeout, keep_alive, threads)
