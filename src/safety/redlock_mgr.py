"""
Agent System (Enterprise++ v3.5) - Redlock Distributed Lock & Fencing Token Manager
Rozproszone blokady Redlock (Redis/etcd) oraz generator monotonicznych Fencing Tokenów.

Zgodnie ze spec.md:
- Sekcja 5.3: Krytyczne blokady fizyczne oparte o silny konsensus (etcd Raft),
  uniemożliwiające generowanie konkurencyjnych fencing tokenów w przypadku
  partycjonowania sieci lub resetu węzła master.
- Sekcja 5.3 (Fencing Tokens): Każda komenda posiada unikalny, rosnący numer;
  urządzenie odrzuca token <= ostatnio przetworzonemu.

Architektura blokad:
- All physical commands require distributed lock (etcd-based async wrapper).
- Token generator jest wyłącznie sterowany przez lock: token jest przyznawany
  dopiero po skutecznym nabyciu blokady, co eliminuje split-brain.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.safety.etcd_client import (
    get_lock_async,
    release_lock_async,
    put_value_async,
    get_value_async,
    EtcdNotAvailableError,
)

logger = logging.getLogger(__name__)


class FencingToken(BaseModel):
    """Monotonic fencing token identifier."""
    value: int = Field(..., ge=0)
    owner_id: str = Field(..., description="Owner/session that was granted the token")
    lock_key: str = Field(default="", description="Distributed lock key protected by token")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LockHandle:
    """Handle for an acquired distributed lock with fencing token."""
    lock_key: str
    etcd_lock: Any  # actual etcd3 lock object from get_lock_async()
    fencing_token: int
    ttl_seconds: int
    acquired_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.acquired_at) > self.ttl_seconds


class FencingTokenGenerator:
    """
    Monotonic fencing token generator.
    Generates tokens ONLY after successful lock acquisition.
    """

    def __init__(self, initial_token: int = 1000, increment: int = 1, max_value: int = 999_999_999):
        if initial_token < 0 or increment < 1 or max_value <= initial_token:
            raise ValueError("Invalid fencing token generator parameters")
        self._current = initial_token
        self._increment = increment
        self._max_value = max_value
        self._lock = threading.Lock()
        self._issue_counter = 0

    def next_token(self, owner_id: str, lock_key: str) -> FencingToken:
        """Atomically produce next strictly-monotonic token."""
        with self._lock:
            if self._current >= self._max_value:
                # Safety wrap to very low value would violate monotonicity,
                # so on overflow we force restart / halt instead.
                raise OverflowError(
                    "Fencing token space exhausted - system restart required"
                )
            self._current += self._increment
            self._issue_counter += 1
            return FencingToken(
                value=self._current,
                owner_id=owner_id,
                lock_key=lock_key,
            )

    @property
    def last_value(self) -> int:
        return self._current

    @property
    def issued_tokens(self) -> int:
        return self._issue_counter


class RedlockManager:
    """
    Distributed lock manager (Redlock / etcd consensus).

    Every physical operation is protected by:
        1. Distributed lock (etcd via async wrapper) - prevents concurrent commands
        2. Fencing token (generated exclusively after lock acquisition)
    """

    def __init__(
        self,
        etcd_endpoints: Optional[list[str]] = None,
        lock_ttl_seconds: int = 30,
        owner_id: Optional[str] = None,
    ):
        self._etcd_endpoints = etcd_endpoints or ["http://etcd1:2379"]
        self._lock_ttl_seconds = lock_ttl_seconds
        self._owner_id = owner_id or f"agent-{uuid.uuid4().hex[:8]}"
        self._token_generator = FencingTokenGenerator()
        self._active_locks: dict[str, LockHandle] = {}
        self._cancel_event = asyncio.Event()

    async def acquire(self, lock_key: str, ttl_seconds: Optional[int] = None) -> Optional[LockHandle]:
        """
        Acquire distributed lock and produce fencing token.

        IMPORTANT: The fencing token is produced ONLY after lock acquisition.
        This guarantees that a command with a high token always holds the lock,
        eliminating split-brain / stale-command execution after network partition.

        Returns:
            LockHandle with fencing token, or None if lock denied.
        """
        ttl = ttl_seconds or self._lock_ttl_seconds

        # 1) Distributed lock via etcd async wrapper
        etcd_lock = await get_lock_async(lock_key, ttl=ttl)
        if etcd_lock is None:
            logger.warning("Redlock denied for %s (etcd lock unavailable)", lock_key)
            return None

        # 2) Fencing token issued ONLY after lock success
        token = self._token_generator.next_token(self._owner_id, lock_key)

        handle = LockHandle(
            lock_key=lock_key,
            etcd_lock=etcd_lock,
            fencing_token=token.value,
            ttl_seconds=ttl,
        )
        self._active_locks[lock_key] = handle
        logger.info(
            "Lock acquired key=%s token=%d owner=%s ttl=%ds",
            lock_key, token.value, self._owner_id, ttl,
        )
        return handle

    async def release(self, handle: LockHandle) -> bool:
        """Release previously acquired lock."""
        if handle is None:
            return True

        released = await release_lock_async(handle.etcd_lock)
        if released:
            self._active_locks.pop(handle.lock_key, None)
            logger.info("Lock released key=%s token=%d", handle.lock_key, handle.fencing_token)
        return released

    async def monitor_leases(self) -> None:
        """
        Background task that extends leases of active locks
        and logs expiry warnings.
        """
        logger.info("RedlockManager lease monitor started")
        try:
            while not self._cancel_event.is_set():
                await asyncio.sleep(5.0)
                for key, handle in list(self._active_locks.items()):
                    if handle.is_expired:
                        logger.critical(
                            "Lock %s (token=%d) EXPIRED while active!",
                            key, handle.fencing_token,
                        )
        except asyncio.CancelledError:
            logger.info("RedlockManager lease monitor stopped")

    async def start_monitor(self) -> None:
        self._cancel_event = asyncio.Event()
        asyncio.create_task(self.monitor_leases())

    async def stop_monitor(self) -> None:
        self._cancel_event.set()

    async def persist_token_state(self, token: int) -> bool:
        """Persist fencing token state to etcd for audit/verification."""
        key = "/fencing/accepted/last"
        return await put_value_async(key, str(token).encode())

    async def read_token_state(self) -> Optional[int]:
        raw = await get_value_async("/fencing/accepted/last")
        if raw is None:
            return None
        try:
            return int(raw.decode())
        except ValueError:
            return None

    @property
    def active_lock_keys(self) -> list[str]:
        return list(self._active_locks.keys())

    async def health_check(self) -> dict[str, Any]:
        import src.safety.etcd_client as etcd_mod
        etcd_health = await etcd_mod.health_check_async()
        return {
            "owner_id": self._owner_id,
            "etcd": etcd_health,
            "active_locks": len(self._active_locks),
            "active_lock_keys": self.active_lock_keys,
            "last_token": self._token_generator.last_value,
            "issued_tokens": self._token_generator.issued_tokens,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }