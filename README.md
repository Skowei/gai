# 🤖 AI Ecosystem V2.0 — 100% Lokalny System AI

**Czytaj w języku Polski!**

## 📋 Spis Treści

- [🏗️ Architektura](#-architektura)
- [🔧 Instalacja i Uruchomienie](#-instalacja-i-uruchomienie)
- [🎯 Użycie](#-użycie)
- [📦 Backup/Restore](#-backuprestore)
- [🔒 Bezpieczeństwo SQL](#-bezpieczeństwo-sql)
- [⚙️ Konfiguracja](#-konfiguracja)

---

## 🏗️ Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Ecosystem V2.0                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────┐    ┌──────────────────────┐       │
│  │   Ollama (GPU)       │    │   Semantic Cache      │       │
│  │  • qwen2.5-coder     │────▶│   Redis 7            │       │
│  │  • deepseek-r1       │◀───▶│   (L0/L3)           │       │
│  │  • llama3.1          │    │                       │       │
│  │  • qwen2-vl          │    └──────────────────────┘       │
│  │  • bge-m3            │                                     │
│  └──────────────────────┘                                     │
│                      │                                         │
│                      ▼                                         │
│  ┌──────────────────────┐    ┌──────────────────────┐       │
│  │   LangGraph           │    │  TencentDB Agent     │       │
│  │   Workflow            │────▶│   Memory (L0-L3)    │       │
│  │                       │    │                       │       │
│  │ ┌──────────┐         │    │  PostgreSQL + pgvector│       │
│  │ │  Router  │─► Code │    │  • RAG queries        │       │
│  │ │          │        │    │  • Long-term memory   │       │
│  │ │ Reasoning│─► Logic│    │                       │       │
│  │ │          │        │    └──────────────────────┘       │
│  │ │ Text     │◀──RAG─▶                                     │
│  │ └──────────┘         │                                     │
│  └──────────────────────┘                                     │
│                                                               │
│  ┌──────────────────────┐    ┌──────────────────────┐       │
│  │   SQL Guardrail      │    │  Tools & Services     │       │
│  │  (READ-ONLY)         │    │  • sql_tool.py        │       │
│  │  SELECT ONLY         │    │  • obsidian_tool.py   │       │
│  └──────────────────────┘    │  • vision_tool.py     │       │
│                              └──────────────────────┘       │
│                                                               │
└─────────────────────────────────────────────────────────────┘

📁 Struktura Danych:
  data/              # Postgres, Redis, Obsidian vault
    ├── postgres_data/
    ├── redis_data/
    └── obsidian_vault/

💾 Backupy (nie w Git!):
  backups/*.zip      # Archiwum do przywracania
```
