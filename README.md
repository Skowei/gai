# 🤖 AI Ecosystem V2.0 — 100% Lokalny System AI

**Czytaj w języku Polski.**

## 📋 Spis Treści

- [🏗️ Architektura](#-architektura)
- [🔧 Instalacja i Uruchomienie](#-instalacja-i-uruchomienie)
- [🎯 Użycie (Interfejsy)](#-użycie-interfejsy)
- [📦 Backup / Restore](#-backup--restore)
- [🔒 Bezpieczeństwo SQL](#-bezpieczeństwo-sql)
- [⚙️ Konfiguracja](#-konfiguracja)

---

## 🏗️ Architektura

```
┌──────────────────────────────────────────────────────────┐
│                    AI Ecosystem V2.0                      │
├──────────────────────────────────────────────────────────┤
│  Interfejsy:    Flask API · GUI tkinter · TUI (curses)    │
│                           │                              │
│                           ▼                              │
│  LangGraph Workflow (src/graph)                          │
│  START → fetch_memory → router → model → tools → ANSWER  │
│     ├─ kod     ─► code_analysis (qwen2.5-coder:7b)        │
│     ├─ logika  ─► reasoning     (qwen3.5:latest)          │
│     └─ tekst   ─► text          (qwen3.5:latest)          │
│                           │                              │
│                           ▼                              │
│  MemoryClient (src/memory)                               │
│   • L0 Redis        — krótkoterminowa cache              │
│   • L1 PostgreSQL   – pamięć z embeddings (pgvector)      │
│   • L3 rag_history  – ostatnie Q&A (okno kontekstu)       │
├──────────────────────────────────────────────────────────┤
│  Ollama (lokalna, no cloud):                             │
│    • qwen2.5-coder:7b   (kod / SQL / XML / SVG)           │
│    • qwen3.5:latest      (logika + tekst)                 │
│    • bge-m3              (opcional, embeddings semantyczne)│
├──────────────────────────────────────────────────────────┤
│  Narzędzia (read-only):                                  │
│    • sql_tool.py     → PostgreSQL, tylko SELECT/SHOW...   │
│    • obsidian_tool.py→ vault Markdown → pgvector          │
│    • guardrails.py   → blok INSERT/UPDATE/DELETE/DROP    │
└──────────────────────────────────────────────────────────┘

📁 Struktura Danych:
  data/
    ├── pg_init/           # inicjalizacja Postgres (agent_memory)
    ├── redis_data/
    └── obsidian_vault/    # notatki Markdown do indeksowania

```

## 🔧 Instalacja i Uruchomienie

**Scenerio lokalny (bez Docker, Ollama już działa):**

```bash
cp .env.example .env            # 1. wpisz realne hasło MemoryClient
pip install -r requirements.txt # 2. zależności

# OPTIONAL — prawdziwe embeddings semantyczne do pamięci:
ollama pull bge-m3

python app.py                   # 3. backend Flask → http://localhost:5000
python gui.py                   # 4. GUI tkinter (interfejs graficzny)
python ai_chat.py               # 5. TUI w terminalu (curses)
```

**Scenerio z Docker (Postgres + Redis + Flask):**

```bash
make up         # buduje i uruchomia wszystkie usługi
make check      # status usług
make down       # zatrzymaj (dane zostają w wolumenach)
```

## 🎯 Użycie (Interfejsy)

- **Backend (app.py)**: `POST /api/chat` body `{"query": "..."}`. `GET /health`.
- **GUI (gui.py)**: wpisz text, ENTER / „Wyślij”. Odpowiedż z Ollamy.
- **TUI (ai_chat.py)**: wpisz wiadomość, ENTER wyślij; `/quit` lub Ctrl+C wyjściej.
- Routing modelari: kod → `qwen2.5-coder`, logika/tekst → `qwen3.5`.

## 📦 Backup / Restore

```bash
make backup     # archiwum do backups/*.zip
make restore    # przywróz (podaj ścieżkę do .zip)
```

## 🔒 Bezpieczeństwo SQL

`src/security/guardrails.py` **blokuje** INSERT / UPDATE / DELETE / DROP —
agent może tylko `SELECT / SHOW / DESCRIBE / EXPLAIN`. 
`sql_tool.py` uruchomia zapy tylko, jeśli są bezpieczne (SELECT).

## ⚙️ Konfiguracja

Zmienne w `.env` / `.env.example` (i docker-compose):

`OLLAMA_BASE_URL`, `CODE_MODEL`, `REASONING_MODEL`, `TEXT_MODEL`,
`EMBEDDING_MODEL`, `MEMORY_PG_USER/PASSWORD/HOST/PORT/DATABASE`, `REDIS_URL`.

> 💡 **Embeddings:** aby RAG / pamięć semantyczna poprawno działała,
> zainstaluj model embeddingowy: `ollama pull bge-m3`.
> Bez niego `MemoryClient` używa deterministycznego zaszępczy (hash),
> który nie crashuje, ale nie jest naprawdzi semantyczny.