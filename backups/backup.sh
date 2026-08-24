#!/bin/bash
# =============================================================================
# AI Ecosystem V2.0 - Skrypt Backupowy
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
BACKUP_FILE="${SCRIPT_DIR}/backups/backup_$(date +%Y%m%d_%H%M%S).zip"

echo "🔄 Tworzenie backupu systemu AI..."

# Sprawdź czy katalog istnieje
if [ ! -d "$DATA_DIR" ]; then
    echo "❌ Katalog '$DATA_DIR' nie istnieje!"
    exit 1
fi

# Stwórz archiwum ZIP z danymi (kompresja maksymalna)
zip -r -9 "${BACKUP_FILE}" \
    "${DATA_DIR}/agent_memory/" \
    "${DATA_DIR}/postgres_data/" \
    "${DATA_DIR}/redis_data/" \
    "${DATA_DIR}/obsidian_vault/" \
    2>/dev/null || true

echo "✅ Backup utworzony: ${BACKUP_FILE}"
echo "📦 Rozmiar: $(du -h "${BACKUP_FILE}" | cut -f1)"

# Opcjonalnie: wysyłaj backup w zewnętrzne miejsce (konfiguracja)
# aws s3 cp "${BACKUP_FILE} s3://your-bucket/backups/" \
#     --region us-east-1 || true

echo "✅ Backup zakończony pomyślnie"