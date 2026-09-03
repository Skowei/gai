"""
Agent System (Enterprise++ v3.5) - Qdrant Long-Term Memory Client
Async client for the encrypted Qdrant vector store (Mem0 L0-L4).

Zgodnie ze spec.md:
- Sekcja 3: Qdrant Cluster (Encrypted Volume LUKS2)
- Test 10.2: `QdrantClient.ping()` - warm-start recovery detection
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QdrantConfig(BaseModel):
    """Configuration schema for the Qdrant long-term memory client."""
    host: str = Field(default="qdrant", description="Qdrant server hostname")
    port: int = Field(default=6334, ge=1, le=65535, description="HTTP port")
    grpc_port: int = Field(default=6335, ge=1, le=65535, description="gRPC port")
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0, description="Request timeout")
    collection_name: str = Field(default="agent_memory", description="Default collection")


class QdrantSearchHit(BaseModel):
    """Single vector search hit."""
    id: str
    score: float = Field(ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)


class QdrantClient:
    """
    Async wrapper around the Qdrant vector database.

    Fully local/offline: talks to the Qdrant container on the
    `agent_internal` network only. Used by the Memory layer (Mem0)
    and warm-start detection.
    """

    def __init__(
        self,
        host: str = "qdrant",
        port: int = 6333,
        grpc_port: int = 6334,
        api_key: Optional[str] = None,
        collection_name: str = "agent_memory",
        timeout_s: float = 5.0,
        retry_attempts: int = 5,
    ):
        self._host = host
        self._port = port
        self._grpc_port = grpc_port
        self._api_key = api_key
        self._collection_name = collection_name
        self._timeout_s = timeout_s
        self._retry_attempts = retry_attempts
        self._client: Optional[Any] = None
        self._connected = False

    async def connect(self) -> bool:
        """Initialize the async Qdrant client (lazy import, offline only)."""
        def _connect() -> Optional[Any]:
            try:
                from qdrant_client import AsyncQdrantClient  # local only

                return AsyncQdrantClient(
                    host=self._host,
                    port=self._port,
                    grpc_port=self._grpc_port,
                    api_key=self._api_key,
                    timeout=self._timeout_s,
                )
            except ImportError:
                logger.warning("qdrant-client not installed - memory layer degraded")
                return None
            except Exception as exc:
                logger.error("Qdrant connect failed: %s", exc)
                return None

        self._client = await asyncio.to_thread(_connect)
        self._connected = self._client is not None
        if self._connected:
            logger.info("QdrantClient connected: %s:%d", self._host, self._port)
        return self._connected

    async def ping(self) -> bool:
        """
        Availability probe (spec test 10.2).
        Returns True when the Qdrant service answers.
        """
        if self._client is None:
            # Raw TCP fallback probe when client lib unavailable
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=self._timeout_s,
                )
                writer.close()
                await writer.wait_closed()
                return True
            except (OSError, asyncio.TimeoutError):
                return False

        for attempt in range(1, self._retry_attempts + 1):
            try:
                await self._client.get_collections()
                return True
            except Exception as exc:
                logger.warning("Qdrant ping attempt %d/%d failed: %s",
                               attempt, self._retry_attempts, exc)
                await asyncio.sleep(0.2 * attempt)
        return False

    async def search(
        self,
        collection: Optional[str] = None,
        query_vector: Optional[list[float]] = None,
        limit: int = 10,
        score_threshold: float = 0.7,
    ) -> list[QdrantSearchHit]:
        """Vector similarity search against long-term memory."""
        if self._client is None or query_vector is None:
            return []
        try:
            hits = await self._client.query_points(
                collection_name=collection or self._collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )
            return [
                QdrantSearchHit(
                    id=str(p.id),
                    score=float(p.score),
                    payload=dict(p.payload or {}),
                )
                for p in getattr(hits, "points", [])
            ]
        except Exception as exc:
            logger.error("Qdrant search failed: %s", exc)
            return []

    async def upsert(
        self,
        points: list[dict[str, Any]],
        collection: Optional[str] = None,
    ) -> bool:
        """Upsert memory points (payload + vector)."""
        if self._client is None:
            return False
        try:
            await self._client.upsert(
                collection_name=collection or self._collection_name,
                points=points,
                wait=True,
            )
            return True
        except Exception as exc:
            logger.error("Qdrant upsert failed: %s", exc)
            return False

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
        self._connected = False

    async def health_check(self) -> dict[str, Any]:
        start = time.time()
        ok = await self.ping()
        return {
            "connected": self._connected,
            "reachable": ok,
            "latency_ms": (time.time() - start) * 1000,
            "host": self._host,
            "port": self._port,
            "collection": self._collection_name,
        }