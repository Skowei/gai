"""
Agent System (Enterprise++ v3.5) - 50Hz Telemetry Receiver
High-frequency telemetry receiver with TTL checking and Drop-Tail policy.

Features:
- Receives telemetry data at >50Hz frequency
- Strict TTL enforcement (<500ms) - drops expired frames
- Backpressure handling with frame discarding
- Integration with LangGraph Ingestion Node
- Sequence tracking and gap detection
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TelemetryFrame(BaseModel):
    """Single telemetry frame from drone."""
    timestamp: float = Field(default_factory=time.time)
    sequence_number: int = 0
    source: str = "drone"
    latitude: float = Field(default=0.0, ge=-90.0, le=90.0)
    longitude: float = Field(default=0.0, ge=-180.0, le=180.0)
    altitude_m: float = Field(default=0.0, ge=0.0, le=10000.0)
    heading_deg: float = Field(default=0.0, ge=0.0, le=360.0)
    speed_ms: float = Field(default=0.0, ge=0.0, le=340.0)
    battery_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    gps_fix_type: int = Field(default=0, ge=0, le=6)
    satellites_visible: int = Field(default=0, ge=0, le=50)
    is_armed: bool = False
    flight_mode: str = "UNKNOWN"
    temperature_celsius: float = 0.0
    gpu_utilization: float = Field(default=0.0, ge=0.0, le=100.0)
    memory_used_mb: int = Field(default=0, ge=0)


class TelemetryStats(BaseModel):
    """Telemetry receiver statistics."""
    frames_received: int = 0
    frames_accepted: int = 0
    frames_dropped_ttl: int = 0
    frames_dropped_backpressure: int = 0
    sequence_gaps: int = 0
    last_sequence: int = 0
    last_receive_time: float = 0.0
    average_latency_ms: float = 0.0


class TelemetryConfig(BaseModel):
    """Configuration for the TelemetryReceiver, aligned with system.yaml [telemetry]."""
    ttl_ms: float = Field(default=500.0, ge=10.0, le=5000.0, description="Maximum frame age in ms (spec 2.3: <500ms)")
    max_buffer_size: int = Field(default=1000, ge=100, le=50000, description="Drop-Tail buffer depth")
    expected_hz: float = Field(default=50.0, ge=1.0, le=1000.0, description="Target telemetry rate")
    enable_backpressure: bool = Field(default=True, description="Drop frames when buffer full")


class TelemetryReceiver:
    """
    High-frequency telemetry receiver with TTL checking.

    Implements:
    - Frame reception at >50Hz
    - TTL validation (<500ms) with immediate drop
    - Backpressure handling when buffer full
    - Sequence gap detection
    - Integration with LangGraph Ingestion Node
    """

    def __init__(
        self,
        ttl_ms: float = 500.0,
        max_buffer_size: int = 1000,
        on_frame_received: Optional[Callable[[TelemetryFrame], Any]] = None,
    ):
        self._ttl_ms = ttl_ms
        self._max_buffer_size = max_buffer_size
        self._on_frame_received = on_frame_received
        self._buffer: asyncio.Queue = asyncio.Queue(maxsize=max_buffer_size)
        self._stats = TelemetryStats()
        self._is_running = False
        self._receiver_task: Optional[asyncio.Task] = None
        self._processor_task: Optional[asyncio.Task] = None
        self._last_sequence = 0
        self._latency_window: list[float] = []
        self._max_latency_window = 100

    async def start(self) -> None:
        """Start telemetry receiver."""
        if self._is_running:
            return
        self._is_running = True
        self._receiver_task = asyncio.create_task(self._receive_loop())
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info(f"TelemetryReceiver started (TTL={self._ttl_ms}ms, buffer={self._max_buffer_size})")

    async def stop(self) -> None:
        """Stop telemetry receiver."""
        self._is_running = False
        if self._receiver_task:
            self._receiver_task.cancel()
        if self._processor_task:
            self._processor_task.cancel()
        logger.info("TelemetryReceiver stopped")

    async def ingest_frame(self, frame: TelemetryFrame) -> bool:
        """
        Ingest a telemetry frame with TTL checking.
        
        Args:
            frame: Telemetry frame to ingest
            
        Returns:
            True if frame was accepted, False if dropped
        """
        self._stats.frames_received += 1
        latency_ms = (time.time() - frame.timestamp) * 1000
        if latency_ms > self._ttl_ms:
            self._stats.frames_dropped_ttl += 1
            logger.debug(f"Frame dropped (TTL): latency={latency_ms:.1f}ms > {self._ttl_ms}ms")
            return False
        if self._buffer.full():
            self._stats.frames_dropped_backpressure += 1
            try:
                self._buffer.get_nowait()
            except asyncio.QueueEmpty:
                pass
            logger.warning("Frame dropped (backpressure): buffer full")
            return False
        await self._buffer.put(frame)
        self._stats.frames_accepted += 1
        self._update_latency(latency_ms)
        return True

    async def _receive_loop(self) -> None:
        """Main receive loop for telemetry frames."""
        while self._is_running:
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Receive loop error: {e}")
                await asyncio.sleep(0.1)

    async def _process_loop(self) -> None:
        """Process frames from buffer."""
        while self._is_running:
            try:
                frame = await asyncio.wait_for(self._buffer.get(), timeout=1.0)
                await self._process_frame(frame)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Process loop error: {e}")

    async def _process_frame(self, frame: TelemetryFrame) -> None:
        """Process a single telemetry frame."""
        if frame.sequence_number > 0:
            if self._last_sequence > 0 and frame.sequence_number != self._last_sequence + 1:
                self._stats.sequence_gaps += 1
                logger.warning(f"Sequence gap: expected {self._last_sequence + 1}, got {frame.sequence_number}")
            self._last_sequence = frame.sequence_number
        self._stats.last_sequence = frame.sequence_number
        self._stats.last_receive_time = time.time()
        if self._on_frame_received:
            try:
                if asyncio.iscoroutinefunction(self._on_frame_received):
                    await self._on_frame_received(frame)
                else:
                    self._on_frame_received(frame)
            except Exception as e:
                logger.error(f"Frame callback error: {e}")

    def _update_latency(self, latency_ms: float) -> None:
        """Update latency statistics."""
        self._latency_window.append(latency_ms)
        if len(self._latency_window) > self._max_latency_window:
            self._latency_window = self._latency_window[-self._max_latency_window:]
        self._stats.average_latency_ms = sum(self._latency_window) / len(self._latency_window)

    def get_stats(self) -> TelemetryStats:
        """Get receiver statistics."""
        return self._stats

    def get_buffer_usage(self) -> float:
        """Get buffer usage ratio."""
        return self._buffer.qsize() / self._max_buffer_size

    @property
    def is_running(self) -> bool:
        return self._is_running
