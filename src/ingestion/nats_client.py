"""
Agent System (Enterprise++ v3.5) - NATS JetStream Client
Async client for high-frequency telemetry streaming with Drop-Tail policy.

Features:
- Async NATS JetStream connection with auto-reconnect
- Strict TTL enforcement (<500ms) with Drop-Tail policy
- Backpressure handling with frame discarding
- Connection health monitoring and automatic recovery
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NATSConfig(BaseModel):
    """NATS JetStream configuration."""
    endpoints: list[str] = Field(default_factory=lambda: ["nats://localhost:4222"])
    stream_name: str = "telemetry"
    subjects: list[str] = Field(default_factory=lambda: ["telemetry.>", "commands.>", "events.>"])
    max_age_ms: int = Field(default=500, ge=100, le=5000)
    max_msgs: int = Field(default=100000, ge=1000, le=10000000)
    max_bytes: int = Field(default=1073741824, ge=1048576, le=107374182400)
    discard_policy: str = "old"
    storage_type: str = "file"
    replicas: int = Field(default=2, ge=1, le=5)
    ack_wait_ms: int = Field(default=500, ge=100, le=30000)
    max_deliver: int = Field(default=3, ge=1, le=10)
    max_ack_pending: int = Field(default=1000, ge=100, le=10000)
    reconnect_wait_ms: int = Field(default=1000, ge=100, le=10000)
    max_reconnect_attempts: int = Field(default=10, ge=1, le=100)


@dataclass
class MessageMetadata:
    """Metadata for received messages."""
    subject: str
    timestamp: float
    sequence: int
    ttl_ms: float
    is_expired: bool
    source: str = "unknown"


class NATSJetStreamClient:
    """
    Async NATS JetStream client with Drop-Tail policy.
    
    Implements:
    - Async connection management with auto-reconnect
    - Stream configuration with TTL and Drop-Tail
    - Backpressure handling
    - Connection health monitoring
    """

    def __init__(self, config: NATSConfig):
        self._config = config
        self._nc: Optional[Any] = None
        self._js: Optional[Any] = None
        self._is_connected = False
        self._is_running = False
        self._reconnect_count = 0
        self._messages_received = 0
        self._messages_dropped = 0
        self._last_error: Optional[str] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._subscriptions: list[Any] = []

    async def connect(self) -> bool:
        """Connect to NATS JetStream."""
        try:
            import nats
            self._nc = await nats.connect(
                servers=self._config.endpoints,
                reconnect_time_wait=self._config.reconnect_wait_ms / 1000.0,
                max_reconnect_attempts=self._config.max_reconnect_attempts,
                disconnected_cb=self._on_disconnected,
                reconnected_cb=self._on_reconnected,
                error_cb=self._on_error,
                closed_cb=self._on_closed,
            )
            self._js = self._nc.jetstream()
            await self._setup_stream()
            self._is_connected = True
            self._is_running = True
            logger.info(f"Connected to NATS at {self._config.endpoints}")
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            return True
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to connect to NATS: {e}")
            return False

    async def _setup_stream(self) -> None:
        """Setup JetStream with Drop-Tail policy."""
        try:
            await self._js.add_stream(
                name=self._config.stream_name,
                subjects=self._config.subjects,
                max_age=self._config.max_age_ms / 1000.0,
                max_msgs=self._config.max_msgs,
                max_bytes=self._config.max_bytes,
                discard=self._config.discard_policy,
                storage=self._config.storage_type,
                replicas=self._config.replicas,
            )
            logger.info(f"Stream '{self._config.stream_name}' configured with TTL={self._config.max_age_ms}ms")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info(f"Stream '{self._config.stream_name}' already exists")
            else:
                raise

    async def publish(self, subject: str, data: dict[str, Any]) -> bool:
        """Publish message to JetStream."""
        if not self._is_connected:
            logger.warning("Cannot publish: not connected")
            return False
        try:
            payload = json.dumps(data).encode()
            await self._js.publish(subject, payload)
            return True
        except Exception as e:
            logger.error(f"Failed to publish to {subject}: {e}")
            return False

    async def subscribe(
        self,
        subject: str,
        callback: Callable[[MessageMetadata, dict[str, Any]], Any],
        durable: str = "default",
    ) -> bool:
        """Subscribe to JetStream subject with callback."""
        if not self._is_connected:
            logger.warning("Cannot subscribe: not connected")
            return False
        try:
            import nats
            async def msg_handler(msg):
                try:
                    self._messages_received += 1
                    ttl = (time.time() - msg.metadata.timestamp) * 1000
                    is_expired = ttl > self._config.max_age_ms
                    if is_expired:
                        self._messages_dropped += 1
                        await msg.ack()
                        return
                    metadata = MessageMetadata(
                        subject=msg.subject,
                        timestamp=msg.metadata.timestamp,
                        sequence=msg.metadata.sequence.stream,
                        ttl_ms=ttl,
                        is_expired=is_expired,
                    )
                    data = json.loads(msg.data.decode())
                    await msg.ack()
                    if asyncio.iscoroutinefunction(callback):
                        await callback(metadata, data)
                    else:
                        callback(metadata, data)
                except json.JSONDecodeError:
                    await msg.ack()
                except Exception as e:
                    logger.error(f"Message handler error: {e}")
                    await msg.nak()

            sub = await self._js.subscribe(
                subject,
                cb=msg_handler,
                durable=durable,
            )
            self._subscriptions.append(sub)
            logger.info(f"Subscribed to {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe to {subject}: {e}")
            return False

    async def close(self) -> None:
        """Close NATS connection."""
        self._is_running = False
        if self._health_check_task:
            self._health_check_task.cancel()
        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        if self._nc:
            try:
                await self._nc.close()
            except Exception:
                pass
        self._is_connected = False
        logger.info("NATS connection closed")

    async def _health_check_loop(self) -> None:
        """Health check loop for connection monitoring."""
        while self._is_running:
            try:
                if self._nc and not self._nc.is_connected:
                    self._is_connected = False
                    logger.warning("NATS disconnected - attempting reconnect")
                    await asyncio.sleep(self._config.reconnect_wait_ms / 1000.0)
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(5.0)

    def _on_disconnected(self) -> None:
        self._is_connected = False
        logger.warning("Disconnected from NATS")

    def _on_reconnected(self) -> None:
        self._is_connected = True
        self._reconnect_count += 1
        logger.info(f"Reconnected to NATS (attempt {self._reconnect_count})")

    def _on_error(self, e: Exception) -> None:
        self._last_error = str(e)
        logger.error(f"NATS error: {e}")

    def _on_closed(self) -> None:
        self._is_connected = False
        logger.info("NATS connection closed")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "connected": self._is_connected,
            "messages_received": self._messages_received,
            "messages_dropped": self._messages_dropped,
            "reconnect_count": self._reconnect_count,
            "last_error": self._last_error,
        }
