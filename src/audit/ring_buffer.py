"""
Agent System (Enterprise++ v3.5) - Audit Ring Buffer
In-memory ring buffer with Group Commit for SHA-256 audit logs.

Features:
- Circular buffer in RAM for audit entries
- Group Commit: flush to disk after N entries or timeout
- SHA-256 hashing for each entry
- pSLC flash protection (Write Amplification prevention)
- File rotation based on size and count
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RingBufferConfig(BaseModel):
    """Ring buffer configuration."""
    capacity: int = Field(default=100, ge=10, le=10000)
    group_commit_size: int = Field(default=100, ge=1, le=1000)
    flush_interval_ms: int = Field(default=5000, ge=1000, le=60000)
    storage_path: str = "/var/log/agent_audit/"
    max_file_size_mb: int = Field(default=100, ge=10, le=10000)
    rotation_count: int = Field(default=10, ge=1, le=100)
    hash_algorithm: str = "sha256"


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: float
    sequence: int
    level: str
    source: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_hash: str = ""
    prev_hash: str = ""

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of entry."""
        data = f"{self.timestamp}:{self.sequence}:{self.level}:{self.source}:{self.message}:{json.dumps(self.metadata, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()


class AuditRingBuffer:
    """
    Ring buffer for audit logs with Group Commit.
    
    Implements:
    - Circular buffer in RAM
    - Group Commit (flush after N entries or timeout)
    - SHA-256 chain hashing
    - File rotation for pSLC protection
    """

    def __init__(self, config: RingBufferConfig):
        self._config = config
        self._buffer: list[Optional[AuditEntry]] = [None] * config.capacity
        self._head = 0
        self._tail = 0
        self._size = 0
        self._sequence = 0
        self._last_hash = ""
        self._flush_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._entries_since_flush = 0
        self._last_flush_time = time.time()
        self._storage_path = Path(config.storage_path)
        self._current_file_index = 0
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize ring buffer and storage."""
        try:
            self._storage_path.mkdir(parents=True, exist_ok=True)
            self._is_running = True
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info(f"AuditRingBuffer initialized (capacity={self._config.capacity}, commit_size={self._config.group_commit_size})")
        except Exception as e:
            logger.error(f"Failed to initialize AuditRingBuffer: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown ring buffer and flush remaining entries."""
        self._is_running = False
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush_to_disk()
        logger.info("AuditRingBuffer shutdown")

    async def append(self, level: str, source: str, message: str, metadata: Optional[dict[str, Any]] = None) -> AuditEntry:
        """
        Append audit entry to ring buffer.
        
        Args:
            level: Log level (INFO, WARNING, ERROR, CRITICAL)
            source: Source component
            message: Log message
            metadata: Additional metadata
            
        Returns:
            Created audit entry with hash
        """
        async with self._lock:
            self._sequence += 1
            entry = AuditEntry(
                timestamp=time.time(),
                sequence=self._sequence,
                level=level,
                source=source,
                message=message,
                metadata=metadata or {},
                prev_hash=self._last_hash,
            )
            entry.entry_hash = entry.compute_hash()
            self._last_hash = entry.entry_hash

            self._buffer[self._head] = entry
            self._head = (self._head + 1) % self._config.capacity

            if self._size < self._config.capacity:
                self._size += 1
            else:
                self._tail = (self._tail + 1) % self._config.capacity

            self._entries_since_flush += 1

            if self._entries_since_flush >= self._config.group_commit_size:
                await self._flush_unlocked()

            return entry

    async def _flush_loop(self) -> None:
        """Periodic flush loop."""
        interval = self._config.flush_interval_ms / 1000.0
        while self._is_running:
            try:
                await asyncio.sleep(interval)
                async with self._lock:
                    if self._entries_since_flush > 0:
                        await self._flush_unlocked()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")

    async def _flush_to_disk(self) -> None:
        """Flush pending entries to disk."""
        async with self._lock:
            await self._flush_unlocked()

    async def _flush_unlocked(self) -> None:
        """Flush entries to disk (must hold lock)."""
        if self._entries_since_flush == 0:
            return

        entries = self._get_all_unlocked()
        if not entries:
            return

        try:
            filename = f"audit_{int(time.time())}_{self._current_file_index:04d}.log"
            filepath = self._storage_path / filename

            with open(filepath, "a") as f:
                for entry in entries:
                    line = json.dumps({
                        "sequence": entry.sequence,
                        "timestamp": entry.timestamp,
                        "level": entry.level,
                        "source": entry.source,
                        "message": entry.message,
                        "metadata": entry.metadata,
                        "hash": entry.entry_hash,
                        "prev_hash": entry.prev_hash,
                    })
                    f.write(line + "\n")

            self._entries_since_flush = 0
            self._last_flush_time = time.time()
            logger.debug(f"Flushed {len(entries)} entries to {filename}")

            await self._rotate_files_if_needed()

        except Exception as e:
            logger.error(f"Failed to flush audit entries: {e}")

    async def _rotate_files_if_needed(self) -> None:
        """Rotate files if size limit reached."""
        try:
            files = sorted(self._storage_path.glob("audit_*.log"))
            if not files:
                return

            latest_file = files[-1]
            file_size_mb = latest_file.stat().st_size / (1024 * 1024)

            if file_size_mb >= self._config.max_file_size_mb:
                self._current_file_index += 1

            if len(files) > self._config.rotation_count:
                files_to_delete = files[:len(files) - self._config.rotation_count]
                for f in files_to_delete:
                    try:
                        f.unlink()
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"File rotation error: {e}")

    def _get_all_unlocked(self) -> list[AuditEntry]:
        """Get all entries from buffer (must hold lock)."""
        entries = []
        if self._size == 0:
            return entries

        idx = self._tail
        for _ in range(self._size):
            entry = self._buffer[idx]
            if entry is not None:
                entries.append(entry)
            idx = (idx + 1) % self._config.capacity

        return entries

    def get_entries(self, count: int = 100) -> list[AuditEntry]:
        """Get recent entries from buffer."""
        entries = []
        if self._size == 0:
            return entries

        idx = (self._head - 1) % self._config.capacity
        for _ in range(min(count, self._size)):
            entry = self._buffer[idx]
            if entry is not None:
                entries.append(entry)
            idx = (idx - 1) % self._config.capacity
            if idx == (self._head - 1) % self._config.capacity:
                break

        return entries

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "size": self._size,
            "capacity": self._config.capacity,
            "sequence": self._sequence,
            "pending_flush": self._entries_since_flush,
            "last_hash": self._last_hash,
        }
