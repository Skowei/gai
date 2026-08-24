
"""AI Ecosystem V2.0 - SQL Tool (read-only)
Read-only database interactions zabezpieczone przez guardrails
"""

import psycopg2
from typing import Dict, List, Any, Optional

# Import guardrail
from ..security.guardrails import is_safe_select_query


class SqlTool:
    """
    Narzędzie do read-only SQL queries.
    
    Blokuje wszystkie operacje write (INSERT, UPDATE, DELETE, DROP).
    Dopuszcza tylko SELECT + SHOW, DESCRIBE, EXPLAIN.
    """
    
    def __init__(self):
        self._pg_pool = None
        self._connect()
    
    def _connect(self):
        """Tworzenie poola połączeń PostgreSQL."""
        import os
        
        try:
            host = os.getenv("MEMORY_PG_HOST", "localhost")
            port = int(os.getenv("MEMORY_PG_PORT", 5432))
            database = os.getenv("MEMORY_PG_DATABASE", "ai_memory")
            user = os.getenv("MEMORY_PG_USER", "agent")
            password = os.getenv("MEMORY_PG_PASSWORD", "your_secure_password")
            
            self._pg_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=5,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
        except Exception as e:
            print(f"⚠️ Postgres pool nieudany: {e}")
    
    def _get_connection(self):
        """Pobieranie connection z poola."""
        if not self._pg_pool:
            raise Exception("PostgreSQL pool nieinicjowany!")
        return self._pg_pool.get()
    
    def execute_query(self, query: str) -> Dict[str, Any]:
        """
        Wykonuje bezpieczne zapytanie SQL (read-only).
        
        Args:
            query: Zapytanie SQL do wykonania
            
        Returns:
            Dict: {"success": bool, "query": str, "rows": list/None, "message": str}
            
        Raises:
            SecurityViolation: Jeśli query nie jest bezpieczne (INSERT, UPDATE, itp.)
        """
        
        # Sprawdź czy query jest bezpieczne
        is_safe, violation = is_safe_select_query(query)
        
        if not is_safe:
            return {
                "success": False,
                "query": query[:100] + "..." if len(query) > 100 else query,
                "rows": None,
                "message": f"Security violation: {violation.message}",
                "allowed_queries": f"Dopuszczane: SELECT, SHOW, DESCRIBE, EXPLAIN",
            }
        
        # Wykonanie read-only query
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query)
                
                rows = cur.fetchall()
                
                # Pobranie nazw kolumn
                column_names = [desc[0] for desc in cur.description] if cur.description else []
                
                # Formatowanie wyników jako listę dict (jeśli są wiersze)
                if rows and column_names:
                    formatted_rows = [dict(zip(column_names, row)) for row in rows]
                elif rows:  # Wiersze bez kolumn (np. SHOW TABLES)
                    formatted_rows = [{"_row": row} for row in rows]
                else:
                    formatted_rows = []
                
                return {
                    "success": True,
                    "query": query.strip(),
                    "rows": formatted_rows,
                    "row_count": len(rows),
                    "message": f"Wykonano {len(formatted_rows)} wierszy",
                }
        
        except psycopg2.Error as e:
            return {
                "success": False,
                "query": query[:100] + "..." if len(query) > 100 else query,
                "rows": None,
                "message": f"Database error: {e}",
            }
        
        except Exception as e:
            return {
                "success": False,
                "query": query[:100] + "..." if len(query) > 100 else query,
                "rows": None,
                "message": f"Error: {e}",
            }
    
    def get_tables(self, limit: int = 50) -> List[Dict[str, str]]:
        """Pobieranie listy tabel z bazy."""
        
        query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name LIMIT %s"
        
        result = self.execute_query(query, (limit,))
        
        return result.get("rows", []) if result.get("success") else []
    
    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Pobieranie struktur tabeli (DESCRIBE/SHOW)."""
        
        query = f"DESCRIBE {table_name}"
        
        return self.execute_query(query)


# Singleton instance
_sql_tool_instance = None

def get_sql_tool() -> SqlTool:
    """Zwrot singleton instance SqlTool."""
    global _sql_tool_instance
    if _sql_tool_instance is None:
        _sql_tool_instance = SqlTool()
    return _sql_tool_instance


def execute_sql(query: str) -> Dict[str, Any]:
    """Convenience function do wykonania bezpiecznego query."""
    return get_sql_tool().execute_query(query)
