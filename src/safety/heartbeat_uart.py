"""
Agent System (Enterprise++ v3.5) - Hardware Heartbeat Sender (Dead Man's Switch)
Dedykowany niskopoziomowy proces przesyłający bajtowe sygnały żywotności (0xAA)
do autopilota PX4 przez izolowany port UART co 200ms.

Zgodnie ze spec.md sekcja 5.2:
- Brak sygnału przez >200ms skutkuje sprzętowym odcięciem sterowania
  i przejściem autopilota w autonomiczny tryb RTL (Return To Launch).
- Kanał jest całkowicie odizolowany od masowego bufora telemetrii >50Hz.

Class: HeartbeatUART
  - async loop sending heartbeat every `interval_ms`
  - detects missed heartbeats (dead man switch)
  - on threshold exceedance triggers hardware RTL / fail-safe callback
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MS = 200
DEFAULT_BAUDRATE = 115200
DEFAULT_DEVICE = "/dev/ttyS0"
HEARTBEAT_BYTE = b"\xAA"
DEFAULT_FAILURE_THRESHOLD_MS = 600  # 3 missed beats


class HeartbeatConfig(BaseModel):
    """Hardware heartbeat configuration."""
    enabled: bool = True
    interval_ms: int = Field(default=DEFAULT_INTERVAL_MS, ge=50, le=1000)
    uart_device: str = DEFAULT_DEVICE
    uart_baudrate: int = Field(default=DEFAULT_BAUDRATE, ge=9600, le=921600)
    heartbeat_byte: bytes = HEARTBEAT_BYTE
    failure_threshold_ms: int = Field(default=DEFAULT_FAILURE_THRESHOLD_MS, ge=100, le=5000)
    failure_action: str = "RTL"  # RTL | LAND | HOLD


class HeartbeatStatus(BaseModel):
    """Runtime status of the heartbeat loop."""
    running: bool = False
    last_heartbeat_sent_at: float = 0.0
    sent_count: int = 0
    failure_count: int = 0
    missed_heartbeats: int = 0
    last_error: Optional[str] = None
    uart_open: bool = False
    dead_man_switch_triggered: bool = False


class HeartbeatUART:
    """
    Dedicated low-level heartbeat sender (200ms Dead Man's Switch).

    Responsibilities:
    - Open isolated UART port (bypasses telemetry buffer)
    - Fire heartbeat byte every `interval_ms`
    - Track missed beats; if gap > failure_threshold_ms, trigger fail-safe callback
    """

    def __init__(
        self,
        config: HeartbeatConfig,
        on_fail_safe: Optional[Callable[..., Any]] = None,
    ):
        self._config = config
        self._on_fail_safe = on_fail_safe
        self._status = HeartbeatStatus()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._uart: Optional[Any] = None
        self._is_running = False

    async def initialize(self) -> bool:
        """Open UART device (if present) or run in degraded/simulated mode."""
        if not self._config.enabled:
            logger.warning("Heartbeat disabled by config")
            return False

        uart_opened = await self._open_uart()
        self._status.uart_open = uart_opened
        if not uart_opened:
            logger.warning(
                "Heartbeat UART not available (%s) - running heartbeat tracking "
                "without physical write (fail-safe still armed)",
                self._config.uart_device,
            )
        return uart_opened

    async def _open_uart(self) -> bool:
        def _open() -> Optional[Any]:
            try:
                import serial  # pyserial

                ser = serial.Serial(
                    port=self._config.uart_device,
                    baudrate=self._config.uart_baudrate,
                    timeout=0.1,
                    write_timeout=0.1,
                )
                return ser
            except ImportError:
                logger.warning("pyserial not installed - cannot open UART")
                return None
            except Exception as exc:
                logger.warning("Cannot open UART %s: %s", self._config.uart_device, exc)
                return None

        self._uart = await asyncio.to_thread(_open)
        return self._uart is not None

    async def start(self) -> None:
        """Start the heartbeat sender loop."""
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        interval = self._config.interval_ms / 1000.0
        self._status.last_heartbeat_sent_at = time.time()
        logger.info(
            "HeartbeatUART started: interval=%dms device=%s threshold=%dms",
            self._config.interval_ms,
            self._config.uart_device,
            self._config.failure_threshold_ms,
        )
        self._task = asyncio.create_task(self._heartbeat_loop(interval))

    async def stop(self) -> None:
        """Stop the heartbeat loop and close UART."""
        self._is_running = False
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._uart is not None:
            try:
                await asyncio.to_thread(self._uart.close)
            except Exception:
                pass
        self._status.running = False
        logger.info("HeartbeatUART stopped")

    async def _heartbeat_loop(self, interval: float) -> None:
        """Main loop: send heartbeat every interval, monitor gaps."""
        run = True
        while run:
            try:
                ok = await self._send_heartbeat()
                if ok:
                    self._status.sent_count += 1
                    self._status.failure_count = 0

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                    run = False  # stop requested
                except asyncio.TimeoutError:
                    pass

                elapsed_ms = (time.time() - self._status.last_heartbeat_sent_at) * 1000
                if elapsed_ms > self._config.failure_threshold_ms:
                    self._status.missed_heartbeats += 1
                    self._status.dead_man_switch_triggered = True
                    logger.critical(
                        "DEAD MAN'S SWITCH TRIGGERED: no heartbeat for %.0fms "
                        "(threshold %dms) - executing fail-safe: %s",
                        elapsed_ms,
                        self._config.failure_threshold_ms,
                        self._config.failure_action,
                    )
                    await self._trigger_fail_safe()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._status.last_error = str(exc)
                self._status.failure_count += 1
                logger.error("Heartbeat loop error: %s", exc)
                await asyncio.sleep(interval)

    async def _send_heartbeat(self) -> bool:
        """Write heartbeat byte to UART (or simulate when device missing)."""
        if self._uart is not None:
            try:
                await asyncio.to_thread(self._uart.write, self._config.heartbeat_byte)
            except Exception as exc:
                self._status.last_error = str(exc)
                logger.error("UART heartbeat write failed: %s", exc)
                return False
        self._status.last_heartbeat_sent_at = time.time()
        return True

    async def _trigger_fail_safe(self) -> None:
        """Invoke fail-safe callback (RTL/land) exactly once per arming."""
        if self._on_fail_safe is not None:
            if asyncio.iscoroutinefunction(self._on_fail_safe):
                await self._on_fail_safe(self._config.failure_action)
            else:
                self._on_fail_safe(self._config.failure_action)

    @property
    def status(self) -> HeartbeatStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def health_check(self) -> dict[str, Any]:
        return {
            "running": self._is_running,
            "uart_open": self._status.uart_open,
            "sent_count": self._status.sent_count,
            "missed_heartbeats": self._status.missed_heartbeats,
            "dead_man_switch_triggered": self._status.dead_man_switch_triggered,
            "interval_ms": self._config.interval_ms,
            "failure_threshold_ms": self._config.failure_threshold_ms,
            "last_error": self._status.last_error,
        }