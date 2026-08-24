.PHONY: up down restart backup restore check help

# =============================================================================
# AI Ecosystem V2.0 - Makefile
# =============================================================================

# Kolory dla czytelności terminala
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# -----------------------------------------------------------------------------
# POMOC: wyświetla dostępne komendy
# -----------------------------------------------------------------------------
help:
	@echo "$(BLUE)=== AI Ecosystem V2.0 - Dostępne Komendy ===$(NC)"
	@echo "  make up       - Uruchom wszystkie usługi (Postgres, Redis)"
	@echo "  make down     - Zatrzymaj wszystkie usługi"
	@echo "  make restart  - Zatrzymaj i uruchom ponownie"
	@echo "  make backup   - Stwórz archiwum backupu"
	@echo "  make restore  - Przywróć z ostatniego backupu (podaj ścieżkę jako argument)"
	@echo "  make check    - Sprawdź status usług"
	@echo "  make clean    - Usuń wszystkie dane i wolumeny"
	@echo ""

# -----------------------------------------------------------------------------
# KOMENDA: up - Uruchom wszystkie usługi w tle
# -----------------------------------------------------------------------------
up:
	@$(BLUE)docker-compose up -d$(NC)
	@$(GREEN)✅ Usługi uruchomione w tle$(NC)
	@echo "📝 Oczekiwanie na gotowość baz danych (może potrwać 30s)..."
	@sleep 15
	@$(GREEN)✅ System AI gotowy$(NC)

# -----------------------------------------------------------------------------
# KOMENDA: down - Zatrzymaj wszystkie usługi
# -----------------------------------------------------------------------------
down:
	@$(YELLOW)docker-compose down$(NC)
	@$(YELLOW)⚠️ Usługi zatrzymane (dane w wolumenach nie są kasowane)$(NC)

# -----------------------------------------------------------------------------
# KOMENDA: restart - Zatrzymaj i uruchom ponownie
# -----------------------------------------------------------------------------
restart: down up

# -----------------------------------------------------------------------------
# KOMENDA: backup - Stwórz archiwum backupu
# -----------------------------------------------------------------------------
backup:
	@chmod +x backups/*.sh
	@$(BLUE)./backups/backup.sh$(NC)

# -----------------------------------------------------------------------------
# KOMENDA: restore - Przywróć z backupu
# -----------------------------------------------------------------------------
restore:
	@if [ -n "$(BACKUP_FILE)" ]; then \
		echo "$(BLUE)Przywracanie z: $(BACKUP_FILE)$$(NC)"; \
	else \
		read -p "Podaj ścieżkę do pliku backupu (.zip): " BACKUP_FILE; \
	fi && \
	chmod +x backups/restore.sh && \
	./backups/restore.sh "$(BACKUP_FILE)"

# -----------------------------------------------------------------------------
# KOMENDA: check - Sprawdź status usług
# -----------------------------------------------------------------------------
check:
	@docker-compose ps

# -----------------------------------------------------------------------------
# KOMENDA: clean - Usuń wszystkie dane i wolumeny (OSTRZEŻENIE!)
# -----------------------------------------------------------------------------
clean: down
	@$(YELLOW)⚠️ OSTRZEŻENIE: Ta komenda usunie WSZYSTKIE dane!$(NC)\n\
Naciśnij Ctrl+C aby anulować, lub Enter aby kontynuować\n\
echo -n "$(YELLOW)">/dev/stdin && read
	@docker-compose down -v
	@$(GREEN)✅ Wszystko oczyszczone$(NC)

.DEFAULT_GOAL := up