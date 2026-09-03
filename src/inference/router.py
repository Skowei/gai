"""
Agent System (Enterprise++ v3.5) - Inference Router with Circuit Breaker
Implements Circuit Breaker pattern with Graceful Drainage for thermal management.

Features:
- Circuit Breaker states: CLOSED, OPEN, HALF_OPEN
- Graceful Drainage with inter-token deadline
- Hard cutoff at 85°C threshold
- Automatic fallback to Qwen-2.5-7B model
- Cooldown probe for recovery detection
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class InferenceRequest(BaseModel):
    """Single inference request routed through the Router."""
    model: str
    prompt: str
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class InferenceModel(str, Enum):
    """Available inference models."""
    PRIMARY = "llama-3.1-70b"
    FALLBACK = "qwen-2.5-7b"
    VISION = "yolo-world"


class RouterConfig(BaseModel):
    """Router configuration."""
    failure_threshold: int = Field(default=5, ge=1, le=20)
    recovery_timeout_ms: int = Field(default=30000, ge=5000, le=120000)
    half_open_max_calls: int = Field(default=3, ge=1, le=10)
    inter_token_deadline_ms: int = Field(default=2000, ge=500, le=10000)
    drain_timeout_ms: int = Field(default=5000, ge=1000, le=30000)
    cooldown_probe_interval_ms: int = Field(default=5000, ge=1000, le=30000)


class DrainStatus(BaseModel):
    """Graceful drainage status."""
    is_draining: bool = False
    drain_start_time: float = 0.0
    inter_token_deadline: float = 0.0
    hard_cutoff_initiated: bool = False
    tokens_remaining: int = 0


class RouterMetrics(BaseModel):
    """Router performance metrics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    fallback_requests: int = 0
    circuit_breaker_trips: int = 0
    thermal_throttle_events: int = 0
    hard_cutoff_events: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0


class InferenceRouter:
    """
    Inference Router with Circuit Breaker and Graceful Drainage.
    
    Manages inference requests with:
    - Circuit breaker pattern for fault isolation
    - Graceful drainage for thermal management
    - Automatic model switching based on thermal state
    - Cooldown probe for recovery detection
    """

    def __init__(
        self,
        config: RouterConfig,
        thermal_monitor: Any = None,
    ):
        self._config = config
        self._thermal_monitor = thermal_monitor
        self._state = CircuitBreakerState.CLOSED
        self._active_model = InferenceModel.PRIMARY
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        self._last_success_time = 0.0
        self._drain_status = DrainStatus()
        self._metrics = RouterMetrics()
        self._lock = asyncio.Lock()
        self._drain_task: Optional[asyncio.Task] = None
        self._cooldown_task: Optional[asyncio.Task] = None
        self._is_running = False

    async def initialize(self) -> None:
        """Initialize the router."""
        self._is_running = True
        logger.info(f"InferenceRouter initialized with model: {self._active_model}")

    async def shutdown(self) -> None:
        """Shutdown the router."""
        self._is_running = False
        if self._drain_task:
            self._drain_task.cancel()
        if self._cooldown_task:
            self._cooldown_task.cancel()
        logger.info("InferenceRouter shutdown")

    async def route_request(
        self,
        request: dict[str, Any],
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """
        Route an inference request with circuit breaker protection.
        
        Args:
            request: The inference request payload
            timeout_ms: Request timeout in milliseconds
            
        Returns:
            Inference response dict
        """
        async with self._lock:
            self._metrics.total_requests += 1

            # Check circuit breaker state
            if self._state == CircuitBreakerState.OPEN:
                if self._should_attempt_recovery():
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    self._metrics.rejected_requests += 1
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")

            # Check thermal state
            thermal_flags = await self._check_thermal_state()
            if thermal_flags and thermal_flags.should_hard_cutoff:
                self._metrics.hard_cutoff_events += 1
                await self._initiate_hard_cutoff()
                return await self._fallback_response(request, "thermal_hard_cutoff")

            if thermal_flags and thermal_flags.should_switch_to_fallback:
                self._metrics.thermal_throttle_events += 1
                self._active_model = InferenceModel.FALLBACK
                if not self._drain_status.is_draining:
                    await self._initiate_graceful_drainage(thermal_flags.inter_token_deadline_ms)

            # Execute request
            try:
                response = await self._execute_request(request, timeout_ms)
                await self._on_success()
                return response
            except Exception as e:
                await self._on_failure(e)
                if self._active_model == InferenceModel.FALLBACK:
                    return await self._fallback_response(request, str(e))
                raise

    async def _execute_request(
        self,
        request: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        """Execute inference request on active model."""
        try:
            response = await asyncio.wait_for(
                self._call_model(request),
                timeout=timeout_ms / 1000.0,
            )
            return response
        except asyncio.TimeoutError:
            raise InferenceTimeoutError(f"Request timed out after {timeout_ms}ms")

    async def _call_model(self, request: dict[str, Any]) -> dict[str, Any]:
        """Call the active inference model."""
        model = self._active_model
        logger.debug(f"Calling model: {model}")
        await asyncio.sleep(0.001)
        return {
            "model": model.value,
            "response": "",
            "tokens_used": 0,
            "finish_reason": "stop",
        }

    async def _check_thermal_state(self) -> Optional[Any]:
        """Check current thermal state from monitor."""
        if self._thermal_monitor:
            try:
                return await self._thermal_monitor.check_thermal_status()
            except Exception as e:
                logger.error(f"Failed to check thermal state: {e}")
        return None

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        elapsed = (time.time() - self._last_failure_time) * 1000
        return elapsed >= self._config.recovery_timeout_ms

    async def _on_success(self) -> None:
        """Handle successful request."""
        self._last_success_time = time.time()
        self._metrics.successful_requests += 1

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            self._half_open_calls += 1
            if self._half_open_calls >= self._config.half_open_max_calls:
                self._state = CircuitBreakerState.CLOSED
                self._failure_count = 0
                logger.info("Circuit breaker CLOSED - recovery successful")
        else:
            self._failure_count = max(0, self._failure_count - 1)

    async def _on_failure(self, error: Exception) -> None:
        """Handle failed request."""
        self._last_failure_time = time.time()
        self._failure_count += 1
        self._metrics.failed_requests += 1
        self._metrics.last_failure_time = self._last_failure_time

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            self._metrics.circuit_breaker_trips += 1
            logger.warning(f"Circuit breaker OPEN again after failure: {error}")
        elif self._failure_count >= self._config.failure_threshold:
            self._state = CircuitBreakerState.OPEN
            self._metrics.circuit_breaker_trips += 1
            logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")

    async def _initiate_graceful_drainage(self, inter_token_deadline_ms: int) -> None:
        """Initiate graceful drainage with inter-token deadline."""
        if self._drain_status.is_draining:
            return

        self._drain_status.is_draining = True
        self._drain_status.drain_start_time = time.time()
        self._drain_status.inter_token_deadline = time.time() + (inter_token_deadline_ms / 1000.0)
        self._drain_status.tokens_remaining = 1

        logger.warning(
            f"Graceful drainage initiated: inter_token_deadline={inter_token_deadline_ms}ms, "
            f"drain_timeout={self._config.drain_timeout_ms}ms"
        )

        self._drain_task = asyncio.create_task(self._drainage_loop())

    async def _drainage_loop(self) -> None:
        """Main drainage loop - waits for inter-token deadline then switches."""
        try:
            while self._drain_status.is_draining:
                now = time.time()
                if now >= self._drain_status.inter_token_deadline:
                    logger.info("Inter-token deadline reached - completing drainage")
                    self._active_model = InferenceModel.FALLBACK
                    self._drain_status.is_draining = False
                    break
                drain_elapsed = (now - self._drain_status.drain_start_time) * 1000
                if drain_elapsed >= self._config.drain_timeout_ms:
                    logger.warning("Drain timeout reached - forcing model switch")
                    self._active_model = InferenceModel.FALLBACK
                    self._drain_status.is_draining = False
                    break
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    async def _initiate_hard_cutoff(self) -> None:
        """Initiate hard cutoff - immediate context termination."""
        logger.critical("HARD CUTOFF initiated - immediate context termination")
        self._drain_status.hard_cutoff_initiated = True
        self._drain_status.is_draining = False
        self._active_model = InferenceModel.FALLBACK
        if self._drain_task:
            self._drain_task.cancel()

    async def _fallback_response(
        self,
        request: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Generate fallback response."""
        self._metrics.fallback_requests += 1
        logger.warning(f"Generating fallback response: {reason}")
        return {
            "model": InferenceModel.FALLBACK.value,
            "response": "",
            "tokens_used": 0,
            "finish_reason": "fallback",
            "fallback_reason": reason,
        }

    async def start_cooldown_probe(self) -> None:
        """Start cooldown probe for recovery detection."""
        if self._cooldown_task:
            return
        self._cooldown_task = asyncio.create_task(self._cooldown_loop())

    async def _cooldown_loop(self) -> None:
        """Cooldown probe loop."""
        interval = self._config.cooldown_probe_interval_ms / 1000.0
        while self._is_running:
            try:
                if self._state == CircuitBreakerState.OPEN:
                    thermal_flags = await self._check_thermal_state()
                    if thermal_flags and not thermal_flags.should_throttle:
                        logger.info("Thermal state recovered - attempting circuit close")
                        self._state = CircuitBreakerState.HALF_OPEN
                        self._half_open_calls = 0
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cooldown loop: {e}")
                await asyncio.sleep(interval)

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state

    @property
    def active_model(self) -> InferenceModel:
        """Get current active model."""
        return self._active_model

    @property
    def metrics(self) -> RouterMetrics:
        """Get router metrics."""
        return self._metrics

    @property
    def drain_status(self) -> DrainStatus:
        """Get current drainage status."""
        return self._drain_status

    async def health_check(self) -> dict[str, Any]:
        """Health check for router."""
        return {
            "status": "healthy" if self._is_running else "stopped",
            "circuit_breaker_state": self._state.value,
            "active_model": self._active_model.value,
            "is_draining": self._drain_status.is_draining,
            "failure_count": self._failure_count,
            "metrics": self._metrics.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class InferenceTimeoutError(Exception):
    """Raised when inference request times out."""
    pass
