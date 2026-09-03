"""
Agent System (Enterprise++ v3.5) - Asynchronous etcd Client Wrapper
Moduł zapobiegający blokowaniu głównej pętli zdarzeń asynchronicznych (asyncio)
przez synchroniczne zapytania do etcd. Zgodny ze spec.md sekcja 9.4.

Exposes:
- get_lock_async(key, ttl)  -> Rozproszona blokada etcd (Raft consensus)
- get_value_async(key)      -> Atomowy odczyt wartości
- put_value_async(key, value, lease) -> Atomic write with optional lease
- delete_value_async(key)   -> Atomic delete
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Główny, współdzielony klient bazowy etcd (synchroniczny).
# Inicjalizowany leniwie (lazy) pierwszym razem, potem współdzielony.
_etcd_client: Optional[Any] = None


class EtcdNotAvailableError(Exception):
    """Raised when etcd client is not initialized / unreachable."""


def get_etcd_client(host: str = "etcd1", port: int = 2379, timeout: float = 5.0) -> Any:
    """
    Initialize (once) the base synchronous etcd3 client.
    All operations are executed in a thread executor to avoid blocking asyncio.
    """
    global _etcd_client
    if _etcd_client is None:
        try:
            import etcd3  # noqa: PLC0415

            _etcd_client = etcd3.client(host=host, port=port, timeout=timeout)
            logger.info("etcd base client initialized: %s:%s", host, port)
        except ImportError as exc:  # pragma: no cover - depends on env
            raise EtcdNotAvailableError(
                "etcd3 library not installed - cannot operate distributed locks"
            ) from exc
        except Exception as exc:  # pragma: no cover - depends on env
            raise EtcdNotAvailableError(f"etcd client init failed: {exc}") from exc
    return _etcd_client


async def get_lock_async(key: str, ttl: int = 30) -> Optional[Any]:
    """
    Asynchroniczne nabycie rozproszonej blokady etcd.

    Wywołanie synchronicznych metod etcd odbywa się w osobnym wątku
    (asyncio.to_thread), aby nie zamrozić głównej pętli zdarzeń
    LangGraph i telemetrii >50Hz.

    Returns:
        Lock object if acquired, otherwise None.
    """
    client = get_etcd_client()

    def _acquire() -> Optional[Any]:
        try:
            lock = client.lock(key, ttl=ttl)
            acquired = lock.acquire(timeout=5)
            return lock if acquired else None
        except Exception as exc:
            logger.error("etcd lock acquire error for %s: %s", key, exc)
            return None

    return await asyncio.to_thread(_acquire)


async def release_lock_async(lock: Any) -> bool:
    """Asynchroniczne zwolnienie blokady etcd."""
    if lock is None:
        return True

    def _release() -> bool:
        try:
            lock.release()
            return True
        except Exception as exc:
            logger.error("etcd lock release error: %s", exc)
            return False

    return await asyncio.to_thread(_release)


async def get_value_async(key: str) -> Optional[bytes]:
    """
    Asynchroniczny odczyt wartości z etcd.
    Zwraca surowe bajty lub None, jeśli klucz nie istnieje.
    """

    client = get_etcd_client()

    def _get() -> Optional[bytes]:
        try:
            value, _meta = client.get(key)
            return value
        except Exception as exc:
            logger.error("etcd get error for key %s: %s", key, exc)
            return None

    return await asyncio.to_thread(_get)


async def put_value_async(
    key: str,
    value: bytes | str,
    lease_id: Optional[int] = None,
) -> bool:
    """Asynchroniczny zapis wartości z opcjonalnym lease (TTL)."""

    client = get_etcd_client()

    def _put() -> bool:
        try:
            client.put(key, value, lease=lease_id)
            return True
        except Exception as exc:
            logger.error("etcd put error for key %s: %s", key, exc)
            return False

    return await asyncio.to_thread(_put)


async def delete_value_async(key: str) -> bool:
    """Asynchroniczne usunięcie klucza z etcd."""

    client = get_etcd_client()

    def _delete() -> bool:
        try:
            client.delete(key)
            return True
        except Exception as exc:
            logger.error("etcd delete error for key %s: %s", key, exc)
            return False

    return await asyncio.to_thread(_delete)


async def health_check_async() -> dict[str, Any]:
    """Asynchroniczna weryfikacja dostępności etcd."""
    try:
        client = get_etcd_client()
        result = await asyncio.to_thread(lambda: client.status())
        return {"available": True, "status": str(result)}
    except Exception as exc:
        return {"available": False, "status": str(exc)}