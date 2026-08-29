# =============================================================================
# COGNITIVE AI "MONSTER" ECOSYSTEM - KOKPIT STEROWANIA TERMINALA
# =============================================================================

.PHONY: up down restart build logs logs-core shell-core clean vram-clear status help

# Domyślna pomoc po wpisaniu samego 'make'
help:
	@echo "Dostępne komendy sterowania ekosystemem:"
	@echo "  make up           - Uruchamia cały system w tle (FastAPI na porcie 8080)"
	@echo "  make down         - Zatrzymuje wszystkie kontenery"
	@echo "  make restart      - Szybki restart wszystkich usług"
	@echo "  make build        - Wymusza przebudowanie obrazów (np. po zmianie requirements.txt)"
	@echo "  make logs         - Wyświetla strumień logów ze wszystkich usług"
	@echo "  make logs-core    - Śledzi logi głównego mózgu FastAPI (weryfikacja bazy i RAG)"
	@echo "  make shell-core   - Wchodzi do konsoli bash wewnątrz kontenera z kodem Pythona"
	@echo "  make vram-clear   - Wymusza na Ollamie natychmiastowe zwolnienie pamięci karty graficznej"
	@echo "  make clean        - Zatrzymuje kontenery i czyści pliki tymczasowe cache Pythona"
	@echo "  make status       - Sprawdza status uruchomionych kontenerów"

# Uruchomienie infrastruktury
up:
	docker compose up -d
	@echo "🚀 Potwór AI wystartował! FastAPI słucha na bezpiecznym porcie http://localhost:8080"

# Zatrzymanie infrastruktury
down:
	docker compose down
	@echo "🛑 System został bezpiecznie zatrzymany."

# Restart systemu
restart:
	docker compose restart
	@echo "🔄 Wszystkie usługi zostały zrestartowane."

# Wymuszenie budowania od zera (Dockerfile.core)
build:
	docker compose up --build -d
	@echo "🔥 Środowisko zostało przebudowane i uruchomione z nowymi pakietami."

# Logi całego ekosystemu
logs:
	docker compose logs -f

# Precyzyjne logi jądra decyzyjnego (FastAPI / LangGraph)
logs-core:
	docker logs ai_api_core -f

# Wejście do powłoki kontenera Pythona
shell-core:
	docker exec -it ai_api_core /bin/bash

# Ręczny, natychmiastowy zrzut modeli z Twojego GPU 10GB VRAM
vram-clear:
	@echo "🧹 Czyszczę pamięć VRAM Twojej karty graficznej..."
	curl -X POST http://localhost:11434/api/generate -d '{"model": "", "keep_alive": 0}'
	@echo "\n✅ VRAM zwolniony."

# Status kontenerów
status:
	docker compose ps

# Czyszczenie śmieci Pythona i zatrzymanie Dockera
clean: down
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "✨ Pliki tymczasowe Pythona zostały wyczyszczone."
