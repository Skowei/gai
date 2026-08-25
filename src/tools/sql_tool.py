"""
==============================================================================
AI Ecosystem V2.0 - SQL Tool (read-only)
Interakcje z bazą tylko SELECT/SHOW/EXPLAIN — chronione przez guardrails.
==============================================================================
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from ..security.guardrails import (
    is_safe_select_query,
    SecurityViolation,
)

log = logging.getLogger("sql-tool")


class SqlTool:
    """Narzędzie do read-only zapytań SQL. Blokuje INSERT/UPDATE/DELETE/DROP."""

    def __init__(self):
        self._pg_pool = None
        self._connect()

    # ---------------------------------------------------------------- Ustawienie
    def _connect(self) -> None:
        try:
            self._pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=3,
                dsn=self._dsn(),
            )
        except Exception as exc:
            log.warning("Postgres pool nieudany: %s", exc)

    def _dsn(self) -> str:
        return (
            f"host={os.getenv('MEMORY_PG_HOST', 'localhost')} "
            f"port={os.getenv('MEMORY_PG_PORT', '5432')} "
            f"dbname={os.getenv('MEMORY_PG_DATABASE', 'ai_memory')} "
            f"user={os.getenv('MEMORY_PG_USER', 'agent')} "
            f"password={os.getenv('MEMORY_PG_PASSWORD', 'your_secure_password')}"
        )

    def _get_connection(self):
        if not self._pg_pool:
            raise ConnectionError("PostgreSQL pool nieinicjowany!")
        return self._pg_pool.getconn()

    def _release(self, conn) -> None:
        if self._pg_pool:
            self._pg_pool.putconn(conn)

    # -------------------------------------------------------------- Bezpieczeństwo
    def execute_query(self, query: str) -> Dict[str, Any]:
        """
        Wykonuje bezpieczne zapytanie SQL (READ-ONLY).

        Returns:
            {"success": bool, "query": str, "rows": list, "row_count": int,
             "columns": list, "message": str}
        """
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

        if not self._pg_pool:
            return {
                "success": False,
                "query": query[:120],
                "rows": None,
                "row_count": 0,
                "columns": [],
                "message": "Brak połączenia z PostgreSQL (usuń połączenie)",
            }

        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(query)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
            formatted = [dict(r) for r in rows]
            return {
                "success": True,
                "query": query.strip(),
                "rows": formatted,
                "row_count": len(formatted),
                "columns": columns,
                "message": f"Wykonano: {len(formatted)} wierszy",
            }
        except psycopg2.Error as exc:
            return {
                "success": False,
                "query": query[:120],
                "rows": None,
                "row_count": 0,
                "columns": [],
                "message": f"Database error: {exc.pgerror or exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "query": query[:120],
                "rows": None,
                "row_count": 0,
                "columns": [],
                "message": f"Error: {exc}",
            }
        finally:
            if conn is not None:
                self._pg_pool.putconn(conn)

    def get_tables(self, limit: int = 50) -> List[str]:
        """Lista tabel w schema 'public'."""
        result = self.execute_query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name LIMIT %s" % int(limit)
        )
        if not result.get("success"):
            return []
        return [r["table_name"] for r in result.get("rows", [])]

    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Struktura tabeli via information_schema (zamiennik DESCRIBE z MySQL)."""
        return self.execute_query(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = '%s' "
            "ORDER BY ordinal_position" % table_name.replace("'", "''")
        )


# =============================================================================
# SINGLETON + convenience
# =============================================================================

_sql_tool_instance: Optional[SqlTool] = None


def get_sql_tool() -> SqlTool:
    global _sql_tool_instance
    if _sql_tool_instance is None:
        _sql_tool_instance = SqlTool()
    return _sql_tool_instance


def execute_sql(query: str) -> Dict[str, Any]:
    """Wygodna funkcja do bezpiecznego query."""
    return get_sql_tool().execute_query(query)