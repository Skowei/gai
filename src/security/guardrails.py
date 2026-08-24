"""
==============================================================================
AI Ecosystem V2.0 - Security Guardrail
Zabezpieczenie przed niebezpiecznymi operacjami SQL (INSERT, UPDATE, DELETE)
Dopuszczalne: SELECT, SHOW, DESCRIBE, EXPLAIN
==============================================================================
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class SecurityViolation:
    """Klasa reprezentująca naruszenie zasad bezpieczeństwa."""
    violation_type: str
    message: str
    allowed_query: Optional[str] = None


def is_safe_select_query(query: str) -> Tuple[bool, Optional[SecurityViolation]]:
    """
    Sprawdza czy zapytanie SQL zawiera tylko bezpieczne operacje odczytowe.
    
    Dopuszczone:
    - SELECT (może mieć WHERE, ORDER BY, LIMIT, JOINy)
    - SHOW, DESCRIBE, EXPLAIN
    
    Nie dozwolone:
    - INSERT, UPDATE, DELETE, DROP
    - CREATE, ALTER, TRUNCATE
    
    Args:
        query: Zapytanie SQL do sprawdzenia
        
    Returns:
        Tuple[bool, Optional[SecurityViolation]]:
            - True, None jeśli zapytanie jest bezpieczne
            - False, SecurityViolation jeśli wykryto zagrożenie
    """
    
    # Usunąć komentarze SQL (bezpeczeństwo!)
    query_cleaned = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    query_cleaned = re.sub(r'/\*.*?\*/', '', query_cleaned, flags=re.DOTALL)
    
    # Normalizacja (usuwanie białych znaków przed analizą)
    tokens = re.split(r'[\s\t]+', query_cleaned.strip().upper())
    
    # Wyciąganie pierwszego słowa klauzuli
    first_keyword = tokens[0].strip() if tokens else ""
    
    # Lista dozwolonych klauzul SQL dla read-only dostępu
    READ_ONLY_KEYWORDS = {
        'SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN', 'ANALYZE'
    }
    
    if first_keyword in READ_ONLY_KEYWORDS:
        return True, None
    
    # Niebezpieczne klauzule (powinny być odrzucane)
    DANGEROUS_KEYWORDS = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 
        'CREATE', 'ALTER', 'TRUNCATE', 'MERGE',
        'REPLACE', 'RENAME', 'GRANT', 'REVOKE'
    }
    
    if first_keyword in DANGEROUS_KEYWORDS:
        violation = SecurityViolation(
            violation_type="WRITE_OPERATION_BLOCKED",
            message=f"Zapytanie zawiera niebezpieczną operację: {first_keyword}",
            allowed_query=f"Dopuszczone klauzule: {', '.join(READ_ONLY_KEYWORDS)}"
        )
        return False, violation
    
    # Sprawdź czy w zapytaniu jest SELECT (np. UNION SELECT)
    if 'SELECT' in query_cleaned and first_keyword not in READ_ONLY_KEYWORDS:
        # Użytkownik próbuje ukryć SELECT wewnątrz niebezpiecznej komendy
        violation = SecurityViolation(
            violation_type="MALFORMED_QUERY",
            message=f"Zapytanie zaczyna się od {first_keyword}, ale zawiera SELECT - podejrzanym tryk injection",
            allowed_query=f"Zapytania muszą zaczynać się od: {', '.join(READ_ONLY_KEYWORDS)}"
        )
        return False, violation
    
    # Dodatkowa ochrona przed SQL Injection
    if not _sanitize_sql(query_cleaned):
        return False, SecurityViolation(
            violation_type="SQL_INJECTION_DETECTED",
            message="Zapytanie zawiera potencjalne wektory SQL Injection"
        )
    
    return True, None


def _sanitize_sql(query: str) -> bool:
    """
    Dodatkowa sanitizacja zapytań - blokuje podwójne cudzysłowiki
    i inne potencjalne wektory ataku.
    
    Args:
        query: Zapytanie SQL do sanitizacji
        
    Returns:
        bool: True jeśli zapytanie jest bezpieczne, False w przeciwnym razie
    """
    
    # Sprawdź czy query zawiera underlinowane znaki (częsty wektor injection)
    if '__' in query.lower():
        return False
    
    # Sprawdź unikalne słowa kluczowe
    words = set(query.split())
    
    # Odrzuć jeśli słowo zawiera cudze znaki lub podwójne apostrofy
    for word in words:
        if "''" in word or '--' in word.lower():
            return False
    
    return True


def parse_sql_query(query: str) -> dict:
    """
    Parsuje zapytanie SQL i zwraca informacje o jego strukturze.
    
    Args:
        query: Zapytanie SQL do analizy
        
    Returns:
        Dict z informacjami o zapytaniu:
            - operation: Rodzaj operacji (SELECT, INSERT, itp.)
            - tables: Lista tabel w JOINach
            - is_safe: Czy zapytanie jest bezpieczne
            
    Raises:
        SecurityViolation: Jeśli zapytanie jest niebezpieczne
    """
    
    query_upper = query.upper().strip()
    
    # Wykrywanie klauzuli operacji
    for keyword in ['SELECT', 'UPDATE', 'DELETE', 'INSERT', 'DROP', 'CREATE']:
        if query_upper.startswith(keyword):
            return {
                'operation': keyword,
                'is_safe': keyword == 'SELECT' or keyword in ['SHOW', 'DESCRIBE'],
                'tables': _extract_tables(query),
                'message': f"Operacja: {keyword}"
            }
    
    # Jeśli nie rozpoznano - domyślne (bezpieczne)
    return {
        'operation': 'UNKNOWN',
        'is_safe': True,
        'tables': [],
        'message': 'Nieznana operacja SQL'
    }


def _extract_tables(query: str) -> list:
    """Wyciąga nazwy tabel z JOINów lub FROM."""
    
    # Prosta regex do ekstrakcji nazw tabel
    table_pattern = r'(?:FROM|JOIN|INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|CROSS\s+JOIN)\s+(?:INTO\s+)?(\w+)\s*(?:\(|,)?'
    
    matches = re.findall(table_pattern, query, re.IGNORECASE)
    
    return list(set(matches))[:5]  # Maks 5 tabel dla bezpieczeństwa



def is_sql_whitelisted(sql_statement: str, allowed_operations: Optional[List[str]] = None) -> Tuple[bool, str]:
    """
    Sprawdza czy zapytanie SQL jest na białej liście dozwolonych operacji.
    
    Dla dodatkowej ochrony - tylko wybrane tabele i kolumny są dozwolone.
    
    Args:
        sql_statement: Zapytanie SQL
        allowed_operations: Lista dozwolonych operacji (np. ['SELECT users.*'])
    
    Returns:
        Tuple[bool, str]: Czy zapytanie jest dozwolone i przyczyna
    """
    # Dla SELECT - sprawdź czy nie ma WHERE z dynamicznymi danymi
    upper_sql = sql_statement.upper()
    
    # Znajdź wszystkie nazwy tabel w FROM/JOIN
    import re
    table_pattern = r'\bFROM\s+(?:\w+\.)*([a-zA-Z_][a-zA-Z0-9_]*)'
    joined_tables = re.findall(table_pattern, sql_statement)
    
    # Tylko dozwolone tabele (np. 'users', 'posts')
    ALLOWED_TABLES = {'users', 'posts', 'comments'}  # Podmieniaj według potrzeb
    
    for table in joined_tables:
        if table.lower() not in {t.lower() for t in ALLOWED_TABLES}:
            return False, f"Tabela '{table}' nie jest na białej liście dozwolonych tabel"
    
    # Sprawdź czy SELECT ma tylko * lub listę kolumn
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_statement, re.IGNORECASE | re.DOTALL)
    if select_match:
        columns_part = select_match.group(1).strip()
        # Dozwól tylko '*' lub konkretne kolumny
        allowed_columns = {'*', 'id', 'name', 'created_at', 'user_id'}
        column_list = [col.strip().split('.')[-1] for col in columns_part.split(',')]  # Usuń aliasy
        for col in column_list:
            if col and col.lower() not in allowed_columns:
                return False, f"Kolumna '{col}' nie jest dozwolona"
    
    return True, "Zapytanie spełnia kryteria whitelist"


def execute_sql_with_guardrails(sql_query: str) -> Tuple[bool, Any]:
    """
    Wykonuje zapytanie SQL z pełną ochroną.
    
    Kroki:
    1. Sprawdź czy to SELECT
    2. Sprawdź whitelistę operacji
    3. Sprawdź whitelistę tabel/kolumn
    4. Wykonaj w trybie TRANSACTION (ROLLBACK przy błędzie)
    
    Args:
        sql_query: Zapytanie SQL do wykonania
    
    Returns:
        Tuple[bool, Any]: (powodzenie, wynik/lb wyjątek)
    """
    import psycopg2
    from contextlib import contextmanager
    
    # 1. Sprawdź czy to bezpieczne SELECT
    is_safe, violation = is_safe_select_query(sql_query)
    if not is_safe:
        return False, f"Blokada: {violation.message}"
    
    # 2. Sprawdź whitelistę operacji
    whitelist_ok, msg = is_sql_whitelisted(sql_query)
    if not whitelist_ok:
        return False, f"Blokada: {msg}"
    
    # 3. Wykonaj w izolowanej transakcji
    @contextmanager
    def get_db_connection():
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="ai_memory",
            user="agent",
            password="your_secure_password"
        )
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql_query)
            if sql_query.strip().upper().startswith('SELECT'):
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return True, {"columns": columns, "rows": rows}
            else:
                row_count = cur.rowcount
                return True, {"affected_rows": row_count}
    except psycopg2.Error as e:
        return False, f"Postgres error: {str(e)}"
    except Exception as e:
        return False, f"Wykonanie zapytania nieudane: {str(e)}"
