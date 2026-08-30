import logging
from typing import Any, Dict, List, Optional
import asyncpg
from app.core.config import settings
from app.memory.l2.client import UnifiedMemoryManager
# Zachowujemy Twoje dotychczasowe guardrails bezpieczeństwa
from app.security.guardrails import is_safe_select_query, SecurityViolation

log = logging.getLogger("sql-tool")

class AsyncSqlTool:
    """
    Zaawansowane, asynchroniczne narzędzie SQL działające w trybie Read-Only.
    Wykorzystuje wspólną pulę połączeń z UnifiedMemoryManager, eliminując nadmiarowe połączenia.
    """
    def __init__(self, memory_manager: UnifiedMemoryManager):
        self.memory_manager = memory_manager

    async def execute_query(self, query: str) -> Dict[str, Any]:
        """
        Asynchronicznie wykonuje bezpieczne zapytanie SQL (SELECT/SHOW/EXPLAIN).
        Gwarantuje brak blokowania pętli zdarzeń FastAPI/WebSockets.
        """
        # 1. Weryfikacja bezpieczeństwa zapytania (Twoje guardrails)
        is_safe, violation = is_safe_select_query(query)
        if not is_safe:
            assert isinstance(violation, SecurityViolation)
            return {
                "success": False,
                "query": query[:120],
                "rows": None,
                "row_count": 0,
                "columns": [],
                "message": f"Security violation: {violation.message}",
            }

        # Upewniamy się, że pula w menedżerze pamięci została zainicjalizowana
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()

        # 2. Asynchroniczne wykonanie zapytania na bazie danych
        async with self.memory_manager.pool.acquire() as conn:
            try:
                # asyncpg zwraca rekordy, które zachowują się jak słowniki, 
                # ale są zoptymalizowanymi obiektami binarnymi C
                rows = await conn.fetch(query)
                
                # Konwersja na czystą listę słowników Pythona
                formatted_rows = [dict(r) for r in rows]
                columns = list(rows[0].keys()) if rows else []

                return {
                    "success": True,
                    "query": query.strip(),
                    "rows": formatted_rows,
                    "row_count": len(formatted_rows),
                    "columns": columns,
                    "message": f"Wykonano asynchronicznie: zwrócono {len(formatted_rows)} wierszy",
                }
            except asyncpg.PostgresError as exc:
                return {
                    "success": False,
                    "query": query[:120],
                    "rows": None,
                    "row_count": 0,
                    "columns": [],
                    "message": f"Database error: {exc}",
                }
            except Exception as exc:
                return {
                    "success": False,
                    "query": query[:120],
                    "rows": None,
                    "row_count": 0,
                    "columns": [],
                    "message": f"System error: {exc}",
                }

    async def get_tables(self, limit: int = 50) -> List[str]:
        """Asynchronicznie pobiera listę tabel w schemacie publicznym."""
        # Bezpieczne bindowanie parametrów w asyncpg za pomocą symbolu $1 (zapobiega wstrzykiwaniu SQL)
        query = """
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name 
            LIMIT $1;
        """
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()

        async with self.memory_manager.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [r["table_name"] for r in rows]

    async def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Asynchronicznie pobiera strukturę danej tabeli."""
        query = """
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = $1 
            ORDER BY ordinal_position;
        """
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()

        async with self.memory_manager.pool.acquire() as conn:
            rows = await conn.fetch(query, table_name)
            formatted_rows = [dict(r) for r in rows]
            return {
                "success": True,
                "table": table_name,
                "columns": formatted_rows
            }

# =============================================================================
# ASYNC SINGLETON
# =============================================================================
_async_sql_tool_instance: Optional[AsyncSqlTool] = None

def get_async_sql_tool(memory_manager: UnifiedMemoryManager) -> AsyncSqlTool:
    """Zwraca zunifikowaną instancję narzędzia powiązaną z menedżerem pamięci."""
    global _async_sql_tool_instance
    if _async_sql_tool_instance is None:
        _async_sql_tool_instance = AsyncSqlTool(memory_manager)
    return _async_sql_tool_instance
