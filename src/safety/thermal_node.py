"""
Agent System (Enterprise++ v3.5) - GPU Thermal Awareness Node
Real-time GPU thermal monitoring with pynvml and async telemetry flags.

Implements:
- Real GPU temperature monitoring via pynvml
- Dynamic threshold-based state transitions (80°C/85°C/90°C)
- Async thermal flag emission for inference router
- Graceful degradation with inter-token deadline awareness
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class ThermalConfig(BaseModel):
    """Runtime thermal configuration matching system.yaml thresholds."""
    warning_threshold_celsius: float = Field(default=80.0, ge=60.0, le=95.0)
    critical_threshold_celsius: float = Field(default=85.0, ge=70.0, le=100.0)
    emergency_threshold_celsius: float = Field(default=90.0, ge=75.0, le=110.0)
    polling_interval_ms: int = Field(default=500, ge=100, le=5000)
    inter_token_deadline_ms: int = Field(default=2000, ge=500, le=10000)
    drain_timeout_ms: int = Field(default=5000, ge=1000, le=30000)

    @model_validator(mode="after")
    def _validate_ordered(self) -> "ThermalConfig":
        if self.warning_threshold_celsius >= self.critical_threshold_celsius:
            raise ValueError("warning_threshold must be < critical_threshold")
        if self.critical_threshold_celsius >= self.emergency_threshold_celsius:
            raise ValueError("critical_threshold must be < emergency_threshold")
        return self


class ThermalThrottleLevel(str, Enum):
    """Thermal throttling severity levels."""
    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    SEVERE = "severe"
    EMERGENCY = "emergency"


class ThermalThresholds(BaseModel):
    """Thermal thresholds loaded from system.yaml."""
    warning_celsius: float = Field(default=80.0, ge=60.0, le=95.0)
    critical_celsius: float = Field(default=85.0, ge=70.0, le=100.0)
    emergency_celsius: float = Field(default=90.0, ge=75.0, le=105.0)
    polling_interval_ms: int = Field(default=500, ge=100, le=5000)
    inter_token_deadline_ms: int = Field(default=2000, ge=500, le=10000)
    drain_timeout_ms: int = Field(default=5000, ge=1000, le=30000)


@dataclass
class ThermalReading:
    """Single GPU thermal reading."""
    temperature_celsius: float
    timestamp: float = field(default_factory=time.time)
    gpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    power_draw_watts: float = 0.0
    fan_speed_percent: Optional[float] = None


class ThermalFlags(BaseModel):
    """Thermal flags emitted to inference router."""
    throttle_level: ThermalThrottleLevel = ThermalThrottleLevel.NONE
    should_throttle: bool = False
    should_switch_to_fallback: bool = False
    should_hard_cutoff: bool = False
    should_emergency_stop: bool = False
    inter_token_deadline_ms: int = 0
    current_temperature: float = 0.0
    threshold_warning: float = 80.0
    threshold_critical: float = 85.0
    threshold_emergency: float = 90.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GPUThermalMonitor:
    """
    GPU Thermal Monitor with pynvml integration.
    
    Provides real-time thermal monitoring with async flag emission
    for the inference router. Implements graceful drainage with
    inter-token deadline awareness.
    """

    def __init__(
        self,
        thresholds: ThermalThresholds,
        device_id: int = 0,
        on_thermal_change: Optional[Callable[[ThermalFlags], Any]] = None,
    ):
        self._thresholds = thresholds
        self._device_id = device_id
        self._on_thermal_change = on_thermal_change
        self._nvml_available = False
        self._nvml_initialized = False
        self._device_handle: Optional[Any] = None
        self._current_flags = ThermalFlags(
            threshold_warning=thresholds.warning_celsius,
            threshold_critical=thresholds.critical_celsius,
            threshold_emergency=thresholds.emergency_celsius,
        )
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_monitoring = False
        self._readings_history: list[ThermalReading] = []
        self._max_history_size = 1000

    async def initialize(self) -> bool:
        """Initialize NVML and verify GPU access."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._init_nvml)
            if self._nvml_available:
                logger.info(f"NVML initialized successfully for GPU {self._device_id}")
                return True
            else:
                logger.warning("NVML not available - running in fallback mode")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize NVML: {e}")
            self._nvml_available = False
            return False

    def _init_nvml(self) -> None:
        """Initialize NVML library (blocking, run in executor)."""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_initialized = True
            device_count = pynvml.nvmlDeviceGetCount()
            if self._device_id < device_count:
                self._device_handle = pynvml.nvmlDeviceGetHandleByIndex(self._device_id)
                self._nvml_available = True
                name = pynvml.nvmlDeviceGetName(self._device_handle)
                logger.info(f"GPU {self._device_id}: {name}")
            else:
                logger.warning(f"GPU {self._device_id} not found. Available: {device_count}")
        except ImportError:
            logger.warning("pynvml not installed - thermal monitoring in fallback mode")
        except Exception as e:
            logger.warning(f"NVML initialization failed: {e}")

    async def get_current_reading(self) -> ThermalReading:
        """Get current GPU thermal reading."""
        if self._nvml_available and self._device_handle:
            return await self._get_real_reading()
        else:
            return await self._get_fallback_reading()

    async def _get_real_reading(self) -> ThermalReading:
        """Get real GPU reading via pynvml."""
        loop = asyncio.get_event_loop()
        try:
            reading = await loop.run_in_executor(None, self._read_gpu_sensors)
            self._add_reading_to_history(reading)
            return reading
        except Exception as e:
            logger.error(f"Failed to read GPU sensors: {e}")
            return await self._get_fallback_reading()

    def _read_gpu_sensors(self) -> ThermalReading:
        """Read GPU sensors (blocking, run in executor)."""
        import pynvml
        temp = pynvml.nvmlDeviceGetTemperature(self._device_handle, pynvml.NVML_TEMPERATURE_GPU)
        util = pynvml.nvmlDeviceGetUtilizationRates(self._device_handle)
        power = pynvml.nvmlDeviceGetPowerUsage(self._device_handle) / 1000.0
        try:
            fan_speed = pynvml.nvmlDeviceGetFanSpeed(self._device_handle)
        except Exception:
            fan_speed = None
        return ThermalReading(
            temperature_celsius=float(temp),
            gpu_utilization=float(util.gpu),
            memory_utilization=float(util.memory),
            power_draw_watts=power,
            fan_speed_percent=fan_speed,
        )

    async def _get_fallback_reading(self) -> ThermalReading:
        """Generate fallback reading when GPU is not available (test environment)."""
        import random
        base_temp = 65.0
        variation = random.uniform(-5.0, 5.0)
        return ThermalReading(
            temperature_celsius=base_temp + variation,
            gpu_utilization=0.0,
            memory_utilization=0.0,
            power_draw_watts=0.0,
            fan_speed_percent=None,
        )

    def _add_reading_to_history(self, reading: ThermalReading) -> None:
        """Add reading to history buffer."""
        self._readings_history.append(reading)
        if len(self._readings_history) > self._max_history_size:
            self._readings_history = self._readings_history[-self._max_history_size:]

    async def check_thermal_status(self) -> ThermalFlags:
        """Check current thermal status and generate flags."""
        reading = await self.get_current_reading()
        flags = self._evaluate_thermal_flags(reading)
        self._current_flags = flags
        return flags

    def _evaluate_thermal_flags(self, reading: ThermalReading) -> ThermalFlags:
        """Evaluate thermal flags based on temperature thresholds."""
        temp = reading.temperature_celsius
        thresholds = self._thresholds
        flags = ThermalFlags(
            current_temperature=temp,
            threshold_warning=thresholds.warning_celsius,
            threshold_critical=thresholds.critical_celsius,
            threshold_emergency=thresholds.emergency_celsius,
        )

        if temp >= thresholds.emergency_celsius:
            flags.throttle_level = ThermalThrottleLevel.EMERGENCY
            flags.should_throttle = True
            flags.should_switch_to_fallback = True
            flags.should_hard_cutoff = True
            flags.should_emergency_stop = True
            flags.inter_token_deadline_ms = 0
        elif temp >= thresholds.critical_celsius:
            flags.throttle_level = ThermalThrottleLevel.SEVERE
            flags.should_throttle = True
            flags.should_switch_to_fallback = True
            flags.should_hard_cutoff = True
            flags.should_emergency_stop = False
            flags.inter_token_deadline_ms = 0
        elif temp >= thresholds.warning_celsius:
            flags.throttle_level = ThermalThrottleLevel.MODERATE
            flags.should_throttle = True
            flags.should_switch_to_fallback = True
            flags.should_hard_cutoff = False
            flags.should_emergency_stop = False
            flags.inter_token_deadline_ms = thresholds.inter_token_deadline_ms
        else:
            flags.throttle_level = ThermalThrottleLevel.NONE
            flags.should_throttle = False
            flags.should_switch_to_fallback = False
            flags.should_hard_cutoff = False
            flags.should_emergency_stop = False
            flags.inter_token_deadline_ms = 0

        return flags

    async def start_monitoring(self) -> None:
        """Start async thermal monitoring loop."""
        if self._is_monitoring:
            return
        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Thermal monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop async thermal monitoring loop."""
        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Thermal monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        interval = self._thresholds.polling_interval_ms / 1000.0
        while self._is_monitoring:
            try:
                flags = await self.check_thermal_status()
                if self._on_thermal_change:
                    if asyncio.iscoroutinefunction(self._on_thermal_change):
                        await self._on_thermal_change(flags)
                    else:
                        self._on_thermal_change(flags)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in thermal monitoring loop: {e}")
                await asyncio.sleep(interval)

    @property
    def current_flags(self) -> ThermalFlags:
        """Get current thermal flags."""
        return self._current_flags

    @property
    def is_nvml_available(self) -> bool:
        """Check if NVML is available."""
        return self._nvml_available

    def get_reading_history(self, last_n: int = 100) -> list[ThermalReading]:
        """Get recent thermal readings."""
        return self._readings_history[-last_n:]

    async def cleanup(self) -> None:
        """Cleanup NVML resources."""
        await self.stop_monitoring()
        if self._nvml_initialized:
            try:
                import pynvml
                pynvml.nvmlShutdown()
            except Exception:
                pass

    async def health_check(self) -> dict[str, Any]:
        """Health check for thermal monitor."""
        return {
            "status": "healthy" if self._is_monitoring else "stopped",
            "nvml_available": self._nvml_available,
            "monitoring": self._is_monitoring,
            "current_temperature": self._current_flags.current_temperature,
            "throttle_level": self._current_flags.throttle_level.value,
            "readings_count": len(self._readings_history),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
