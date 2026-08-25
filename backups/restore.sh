#!/usr/bin/env bash
# =============================================================================
# AI Ecosystem V2.0 - Dynamiczny proces przywracania danych z płaskiego ZIP-a
# Lokalizacja: /backups/restore.sh
# =============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0;0m'

echo -e "${YELLOW}[*] Rozpoczynanie procesu odtwarzania ekosystemu pamięci...${NC}"

# 1. Wczytanie zmiennych z pliku .env
if [ -f "../.env" ]; then
    export $(grep -v '^#' ../.env | xargs)
else
    echo -e "${RED}[ERRO] Nie znaleziono pliku .env!${NC}"
    exit 1
fi

DB_USER=${POSTGRES_USER:-agent}
DB_NAME=${POSTGRES_DB:-ai_memory}

# 2. Wykrywanie najnowszego pliku ZIP
LATEST_ZIP=$(ls -t ai_ecosystem_data_*.zip 2>/dev/null | head -n 1)

if [ -z "${LATEST_ZIP}" ]; then
    echo -e "${RED}[ERRO] Nie znaleziono plików kopii zapasowej (ai_ecosystem_data_*.zip)!${NC}"
    exit 1
fi

echo -e "${GREEN}[OK] Wykryto najnowszą kopię zapasową: ${LATEST_ZIP}${NC}"
read -p "Czy na pewno chcesz nadpisać obecne dane? (y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}[*] Operacja anulowana.${NC}"
    exit 0
fi

# 3. Rozpakowanie archiwum ZIP do tymczasowego folderu bez dotykania zablokowanego /data
echo -e "${YELLOW}[*] Rozpakowywanie archiwum ZIP do katalogu roboczego...${NC}"
TEMP_RESTORE_DIR="./temp_restore"
mkdir -p "${TEMP_RESTORE_DIR}"

unzip -q "${LATEST_ZIP}" -d "${TEMP_RESTORE_DIR}"

# 4. Sprawdzenie czy pliki struktury rozpakowały się poprawnie
SQL_FILE="${TEMP_RESTORE_DIR}/postgres_dump.sql"
if [ ! -f "${SQL_FILE}" ]; then
    echo -e "${RED}[ERRO] W archiwum ZIP nie znaleziono zrzutu bazy danych SQL!${NC}"
    rm -rf "${TEMP_RESTORE_DIR}"
    exit 1
fi

# 5. Aby uniknąć Permission Denied na plikach SQLite, zlecimy podmianę samemu kontenerowi!
# Podnosimy najpierw kontenery, aby móc wykonać na nich komendy (w uśpionym stanie)
echo -e "${YELLOW}[*] Uruchamianie kontenerów w celu synchronizacji pamięci...${NC}"
docker compose -f ../docker-compose.yml up -d

# Czekamy krótką chwilę na stabilizację kontenera memory-core
sleep 2

echo -e "${YELLOW}[*] Wstrzykiwanie bazy SQLite TencentDB bezpośrednio przez kontener...${NC}"
# Pakujemy rozpakowany folder roboczy do tymczasowego tara i wstrzykujemy go prosto do /data kontenera
tar -cf - -C "${TEMP_RESTORE_DIR}/tdai_memory" . | docker compose -f ../docker-compose.yml exec -T memory-core tar -xf - -C /data/tdai-memory/

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[OK] Pliki SQLite zostały poprawnie podmienione przez Dockera.${NC}"
else
    echo -e "${RED}[ERRO] Wstrzykiwanie plików SQLite do kontenera nie powiodło się!${NC}"
    rm -rf "${TEMP_RESTORE_DIR}"
    exit 1
fi

# 6. Czekanie na pełną gotowość serwera PostgreSQL do przywrócenia bazy
echo -e "${YELLOW}[*] Czekanie na pełną gotowość serwera PostgreSQL...${NC}"
until docker compose -f ../docker-compose.yml exec -T postgres pg_isready -U "${DB_USER}" -d "${DB_NAME}" &>/dev/null; do
    echo -n "."
    sleep 1
done
echo -e "\n${GREEN}[OK] PostgreSQL działa poprawnie.${NC}"

# 7. Wstrzyknięcie bazy danych do PostgreSQL (pgvector)
echo -e "${YELLOW}[*] Wstrzykiwanie danych do bazy PostgreSQL (${DB_NAME})...${NC}"
docker compose -f ../docker-compose.yml exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" < "${SQL_FILE}"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[SUCCESS] Wszystkie dane (Postgres + SQLite) zostały pomyślnie odtworzone!${NC}"
else
    echo -e "${RED}[ERRO] Wystąpił problem podczas importowania struktur SQL do Postgresa.${NC}"
fi

# 8. Ostateczny restart kontenera pamięci, aby wczytał nowo podmienione pliki bazy SQLite
echo -e "${YELLOW}[*] Restartowanie kontenera TencentDB w celu odświeżenia bazy pamięci...${NC}"
docker compose -f ../docker-compose.yml restart memory-core

# 9. Sprzątanie po imporcie
rm -rf "${TEMP_RESTORE_DIR}"
