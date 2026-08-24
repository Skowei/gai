#!/bin/bash
# =============================================================================
# AI Ecosystem V2.0 - Skrypt Przywracania Backupu
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Podaj ścieżkę do pliku backupu (lub ostatni)
BACKUP_FILE="${1:-${SCRIPT_DIR}/backups/backup_*.zip}"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Plik backupu nie znaleziony: $BACKUP_FILE"
    exit 1
fi

echo "📦 Przywracanie z: ${BACKUP_FILE}"

# Wyciągnij zawartość do katalogu data/
unzip -o "${BACKUP_FILE}" -d "${SCRIPT_DIR}/data/"

echo "✅ Przywrócenie zakończone"
echo "📝 Po przywróceniu należy uruchomić: docker-compose up -d"