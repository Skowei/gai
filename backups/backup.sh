#!/usr/bin/env bash
# =============================================================================
# AI Ecosystem V2.0 - Pełny eksport danych przez Docker TAR (Płaska struktura ZIP)
# Lokalizacja: /backups/backup.sh
# =============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0;0m'

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
# Wyciągamy bezwzględną ścieżkę dla pliku wyjściowego ZIP przed operacją cd
OUTPUT_ZIP="$(pwd)/ai_ecosystem_data_${TIMESTAMP}.zip"
TEMP_SQL_FILE="/tmp/postgres_dump_${TIMESTAMP}.sql"
TEMP_RESTORE_DIR="./temp_backup_dir"

echo -e "${YELLOW}[*] Rozpoczynanie tworzenia pełnej kopii zapasowej danych...${NC}"

# 1. Automatyczne wczytanie zmiennych z pliku .env
if [ -f "../.env" ]; then
    export $(grep -v '^#' ../.env | xargs)
else
    echo -e "${RED}[ERRO] Nie znaleziono pliku .env w katalogu głównym projektu!${NC}"
    exit 1
fi

DB_USER=${POSTGRES_USER:-agent}
DB_NAME=${POSTGRES_DB:-ai_memory}

# 2. Sprawdzenie czy kontener Postgres działa
if ! docker compose -f ../docker-compose.yml ps postgres | grep -q "Up"; then
    echo -e "${RED}[ERRO] Kontener 'postgres' nie działa!${NC}"
    exit 1
fi

# 3. Wykonanie zrzutu danych z Postgresa prosto do katalogu tymczasowego /tmp
echo -e "${YELLOW}[*] Zrzucanie struktur i danych z bazy PostgreSQL (${DB_NAME})...${NC}"
docker compose -f ../docker-compose.yml exec -T postgres pg_dump -U "${DB_USER}" -d "${DB_NAME}" > "${TEMP_SQL_FILE}"

if [ $? -ne 0 ] || [ ! -s "${TEMP_SQL_FILE}" ]; then
    echo -e "${RED}[ERRO] Kopia PostgreSQL nie powiodła się!${NC}"
    rm -f "${TEMP_SQL_FILE}"
    exit 1
fi
echo -e "${GREEN}[OK] Zrzut PostgreSQL utworzony pomyślnie.${NC}"

echo -e "${YELLOW}[*] Pobieranie plików pamięci SQLite (Obejście uprawnień)...${NC}"

# 4. Przygotowanie czystej, tymczasowej struktury plików
mkdir -p "${TEMP_RESTORE_DIR}/tdai_memory"
docker compose -f ../docker-compose.yml exec -T memory-core tar -cf - -C /data/tdai-memory . | tar -xf - -C "${TEMP_RESTORE_DIR}/tdai_memory" 2>/dev/null

# Przenosimy nasz zrzut SQL bezpośrednio obok folderu tdai_memory
mv "${TEMP_SQL_FILE}" "${TEMP_RESTORE_DIR}/postgres_dump.sql"

echo -e "${YELLOW}[*] Kompresowanie wszystkich baz danych do płaskiego pliku ZIP...${NC}"

# 5. Przechodzimy do wnętrza folderu roboczego, aby zip nie pakował samej nazwy katalogu 'temp_backup_dir'
if [ -d "${TEMP_RESTORE_DIR}" ]; then
    cd "${TEMP_RESTORE_DIR}"
    # Pakujemy zawartość kropką (bieżący stan), dzięki czemu w ZIP-ie nie ma nadrzędnego folderu
    zip -r "${OUTPUT_ZIP}" ./* > /dev/null
    cd .. # Wracamy bezpiecznie do katalogu /backups
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[SUCCESS] Pełna kopia zapasowa ZIP została utworzona pomyślnie!${NC}\n"
        echo -e "${YELLOW}Plik gotowy do przeniesienia na inne urządzenie:${NC}"
        echo -e "${GREEN}--> ${OUTPUT_ZIP}${NC}\n"
    else
        echo -e "${RED}[ERRO] Błąd podczas tworzenia ostatecznego archiwum ZIP.${NC}"
        rm -rf "${TEMP_RESTORE_DIR}"
        exit 1
    fi
else
    echo -e "${RED}[ERRO] Wystąpił problem z przygotowaniem katalogu kopii zapasowej.${NC}"
    rm -rf "${TEMP_RESTORE_DIR}"
    exit 1
fi

# 6. Czyszczenie katalogu roboczego z komputera
rm -rf "${TEMP_RESTORE_DIR}"
