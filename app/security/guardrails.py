import re
from typing import Optional, Tuple, List, Set
from pydantic import BaseModel

class SecurityViolation(BaseModel):
    """Bezpieczny wątkowo i czytelny dla IDE model naruszenia zasad (Pydantic v2)."""
    violation_type: str
    message: str
    allowed_query: Optional[str] = None

def is_safe_select_query(query: str) -> Tuple[bool, Optional[SecurityViolation]]:
    """
    Analizuje tokeny zapytania SQL za pomocą wyrażeń regularnych i blokuje
    wszelkie operacje zapisu lub modyfikacji struktur danych.
    """
    # 1. Czyszczenie komentarzy SQL (Kluczowy wektor ukrywania ataków SQL Injection)
    query_cleaned = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    query_cleaned = re.sub(r'/\*.*?\*/', '', query_cleaned, flags=re.DOTALL)
    
    # 2. Normalizacja i podział na tokeny (Białe znaki, tabulacje)
    tokens = re.split(r'[\s\t\n\r]+', query_cleaned.strip().upper())
    first_keyword = tokens[0].strip() if tokens else ""
    
    # Twoja oryginalna lista bezpiecznych klauzul odczytowych
    READ_ONLY_KEYWORDS = {'SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN', 'ANALYZE'}
    
    if first_keyword not in READ_ONLY_KEYWORDS:
        # Wykrywanie niebezpiecznych operacji modyfikacji danych
        DANGEROUS_KEYWORDS = {
            'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 
            'ALTER', 'TRUNCATE', 'MERGE', 'REPLACE', 'RENAME', 'GRANT', 'REVOKE'
        }
        
        msg = f"Niedozwolona operacja startowa: {first_keyword if first_keyword else 'PUSTE_ZAPYTANIE'}"
        if first_keyword in DANGEROUS_KEYWORDS:
            msg = f"Wykryto zablokowaną operację modyfikacji struktur/danych: {first_keyword}"
            
        return False, SecurityViolation(
            violation_type="WRITE_OPERATION_BLOCKED",
            message=msg,
            allowed_query=f"Zapytanie musi zaczynać się od: {', '.join(READ_ONLY_KEYWORDS)}"
        )
    
    # 3. Ochrona przed ukrytym wstrzykiwaniem (np. Komenda... UNION SELECT ...)
    # Jeśli zapytanie ma strukturę wielokrotnego zapytania z ';' lub próbuje przemycić modyfikację
    query_upper = query_cleaned.upper()
    FORBIDDEN_SUBSTRINGS = ['INSERT ', 'UPDATE ', 'DELETE ', 'DROP ', 'TRUNCATE ', 'ALTER ', 'CREATE ']
    for substr in FORBIDDEN_SUBSTRINGS:
        if substr in query_upper and first_keyword in READ_ONLY_KEYWORDS:
            return False, SecurityViolation(
                violation_type="STACKED_QUERY_INJECTION",
                message=f"Zapytanie zaczyna się od {first_keyword}, ale zawiera niedozwoloną podkomendę: {substr.strip()}"
            )
            
    # 4. Twoja dodatkowa sanitizacja znaków specjalnych
    if not _sanitize_sql_vectors(query_cleaned):
        return False, SecurityViolation(
            violation_type="SQL_INJECTION_DETECTED",
            message="Zapytanie zawiera niedozwolone sekwencje znaków (np. __, '', --)"
        )
        
    return True, None

def _sanitize_sql_vectors(query: str) -> bool:
    """Weryfikuje czy w zapytaniu nie ma niebezpiecznych sekwencji formatowania tekstu."""
    if '__' in query.lower():
        return False
        
    # Podział tekstu i weryfikacja anomalii w apostrofach i komentarzach
    words = query.split()
    for word in words:
        if "''" in word or '--' in word.lower():
            return False
            
    return True

def extract_tables_from_query(query: str) -> List[str]:
    """Ekstrahuje za pomocą wyrażeń regularnych nazwy tabel użyte w klauzulach FROM oraz JOIN."""
    table_pattern = r'(?:FROM|JOIN|INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|CROSS\s+JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    matches = re.findall(table_pattern, query, re.IGNORECASE)
    return list(set(matches))

async def validate_query_against_schema(query: str, active_tables: Set[str]) -> Tuple[bool, Optional[str]]:
    """
    Dynamiczna walidacja. Porównuje tabele z zapytania z realnymi strukturami 
    pobranymi w czasie rzeczywistym z bazy PostgreSQL.
    """
    extracted = extract_tables_from_query(query)
    for table in extracted:
        if table.lower() not in {t.lower() for t in active_tables}:
            return False, f"Tabela '{table}' nie istnieje w bieżącym schemacie bazy danych."
    return True, None
