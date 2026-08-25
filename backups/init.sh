#!/usr/bin/env bash
# =============================================================================
# AI Ecosystem V2.0 - Skrypt automatycznej inicjalizacji struktur bazy danych
# Lokalizacja: /backup/init.sh
# =============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0;0m'

echo -e "${YELLOW}[*] Uruchamianie weryfikacji bazy danych PostgreSQL...${NC}"

# 1. Sprawdzenie, czy kontener Postgres działa w Dockerze
if ! docker compose -f ../docker-compose.yml ps postgres | grep -q "Up"; then
    echo -e "${RED}[ERRO] Kontener 'postgres' nie jest uruchomiony!${NC}"
    echo -e "${YELLOW}[*] Przejdź do głównego katalogu i uruchom: docker compose up -d${NC}"
    exit 1
fi

# 2. Czekanie na pełną gotowość bazy (aż system Postgres otworzy port)
echo -e "${YELLOW}[*] Czekanie na gotowość serwera PostgreSQL...${NC}"
until docker compose -f ../docker-compose.yml exec -T postgres pg_isready -U agent -d ai_memory &>/dev/null; do
    echo -n "."
    sleep 1
done
echo -e "\n${GREEN}[OK] PostgreSQL jest gotowy do przyjmowania połączeń.${NC}"

# 3. Sprawdzenie, czy tabela agent_memory już istnieje, aby chronić zgromadzone wektory
TABLE_EXISTS=$(docker compose -f ../docker-compose.yml exec -T postgres psql -U agent -d ai_memory -tAn -c "
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = 'agent_memory'
    );
")

if [ "$TABLE_EXISTS" = "t" ]; then
    echo -e "${GREEN}[OK] Tabela 'agent_memory' już istnieje. Pomijam inicjalizację, aby chronić dane.${NC}"
    exit 0
fi

# 4. Bezpieczna inicjalizacja bazy strukturalnej i wektorowej z lokalnego pliku SQL
echo -e "${YELLOW}[!] Brak tabel w bazie. Rozpoczynanie inicjalizacji ze schematu SQL...${NC}"

if [ -f "./schema.sql" ]; then
    # Wstrzyknięcie lokalnego pliku schema.sql prosto do CLI Postgresa w kontenerze
    docker compose -f ../docker-compose.yml exec -T postgres psql -U agent -d ai_memory < ./schema.sql
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[SUCCESS] Baza danych i tabele pgvector zostały pomyślnie zainicjalizowane!${NC}"
    else
        echo -e "${RED}[ERRO] Wystąpił błąd podczas wykonywania skryptu SQL.${NC}"
        exit 1
    fi
else
    echo -e "${RED}[ERRO] Nie znaleziono pliku struktury w bieżącym katalogu: ./schema.sql${NC}"
    exit 1
fi
