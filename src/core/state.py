"""
Agent System (Enterprise++ v3.5) - Core State Management
Pydantic v2 SystemState model with fencing token monotonicity validation.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SystemMode(str, Enum):
    NORMAL = "normal"
    THERMAL_THROTTLE = "thermal_throttle"
    WARM_START_REACTIVE = "warm_start_reactive"
    EMERGENCY_RTL = "emergency_rtl"
    MAINTENANCE = "maintenance"
    SHUTDOWN = "shutdown"


class SafetyStatus(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class ThermalState(str, Enum):
    NOMINAL = "nominal"
    ELEVATED = "elevated"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class InferenceModel(str, Enum):
    PRIMARY = "llama-3.1-70b"
    FALLBACK = "qwen-2.5-7b"
    VISION = "yolo-world"


class FencingTokenState(BaseModel):
    """Fencing token state with strict monotonicity enforcement."""
    current_token: int = Field(default=1000, ge=0)
    last_accepted_token: int = Field(default=999, ge=0)
    token_increment: int = Field(default=1, ge=1, le=1000)
    max_token_value: int = Field(default=999999999, ge=1000)
    strict_monotonicity: bool = True
    reject_equal_tokens: bool = True
    reject_stale_threshold_ms: int = Field(default=1000, ge=100, le=10000)
    last_token_timestamp: float = 0.0
    token_history_hash: str = ""

    @field_validator("current_token")
    @classmethod
    def validate_token_monotonicity(cls, v: int, info) -> int:
        values = info.data
        last_accepted = values.get("last_accepted_token", 0)
        strict = values.get("strict_monotonicity", True)
        reject_equal = values.get("reject_equal_tokens", True)
        if strict:
            if reject_equal and v <= last_accepted:
                raise ValueError(f"Fencing token violation: {v} <= {last_accepted}")
            elif not reject_equal and v < last_accepted:
                raise ValueError(f"Fencing token violation: {v} < {last_accepted}")
        return v

    def generate_next_token(self) -> int:
        next_token = self.current_token + self.token_increment
        if next_token > self.max_token_value:
            next_token = 1000
        self.last_accepted_token = self.current_token
        self.current_token = next_token
        self.last_token_timestamp = time.time()
        self._update_history_hash()
        return next_token

    def validate_incoming_token(self, token: int) -> bool:
        if self.strict_monotonicity:
            if self.reject_equal_tokens:
                return token > self.last_accepted_token
            return token >= self.last_accepted_token
        return True

    def _update_history_hash(self) -> None:
        data = f"{self.last_accepted_token}:{self.current_token}:{self.last_token_timestamp}"
        self.token_history_hash = hashlib.sha256(data.encode()).hexdigest()


class TelemetryState(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    latitude: float = Field(default=0.0, ge=-90.0, le=90.0)
    longitude: float = Field(default=0.0, ge=-180.0, le=180.0)
    altitude_m: float = Field(default=0.0, ge=0.0, le=10000.0)
    heading_deg: float = Field(default=0.0, ge=0.0, le=360.0)
    speed_ms: float = Field(default=0.0, ge=0.0, le=340.0)
    battery_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    gps_fix_type: int = Field(default=0, ge=0, le=6)
    satellites_visible: int = Field(default=0, ge=0, le=50)
    vibration_x: float = 0.0
    vibration_y: float = 0.0
    vibration_z: float = 0.0
    is_armed: bool = False
    flight_mode: str = "UNKNOWN"


class GPUState(BaseModel):
    device_id: int = Field(default=0, ge=0, le=15)
    temperature_celsius: float = Field(default=0.0, ge=0.0, le=120.0)
    thermal_state: ThermalState = ThermalState.NOMINAL
    memory_used_mb: int = Field(default=0, ge=0)
    memory_total_mb: int = Field(default=0, ge=0)
    memory_free_mb: int = Field(default=0, ge=0)
    gpu_utilization_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    memory_utilization_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    power_draw_watts: float = Field(default=0.0, ge=0.0)
    power_limit_watts: float = Field(default=0.0, ge=0.0)
    active_model: InferenceModel = InferenceModel.PRIMARY
    mps_enabled: bool = True
    vram_allocation: dict[str, int] = Field(default_factory=lambda: {"vllm": 50, "roboflow": 30, "tools": 20})

    @model_validator(mode="after")
    def validate_thermal_state(self) -> "GPUState":
        if self.temperature_celsius >= 90:
            self.thermal_state = ThermalState.EMERGENCY
        elif self.temperature_celsius >= 85:
            self.thermal_state = ThermalState.CRITICAL
        elif self.temperature_celsius >= 80:
            self.thermal_state = ThermalState.WARNING
        elif self.temperature_celsius >= 70:
            self.thermal_state = ThermalState.ELEVATED
        else:
            self.thermal_state = ThermalState.NOMINAL
        return self


class SafetyState(BaseModel):
    status: SafetyStatus = SafetyStatus.SAFE
    heartbeat_active: bool = True
    last_heartbeat_ms: float = Field(default_factory=time.time)
    watchdog_active: bool = True
    last_watchdog_feed: float = Field(default_factory=time.time)
    ethernet_connected: bool = True
    uart_connected: bool = True
    gps_spoofing_detected: bool = False
    geofence_breached: bool = False
    rtl_triggered: bool = False
    emergency_land_pending: bool = False


class MemoryState(BaseModel):
    qdrant_available: bool = False
    qdrant_collection_loaded: bool = False
    total_vectors: int = Field(default=0, ge=0)
    last_query_timestamp: float = 0.0
    cache_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    semantic_cache_entries: int = Field(default=0, ge=0)


class AuditState(BaseModel):
    merkle_root_hash: str = ""
    total_entries: int = Field(default=0, ge=0)
    last_flush_timestamp: float = 0.0
    ring_buffer_usage: float = Field(default=0.0, ge=0.0, le=1.0)
    integrity_verified: bool = True
    last_verification_timestamp: float = 0.0


class SystemState(BaseModel):
    """Complete system state for Agent System (Enterprise++ v3.5)."""
    schema_version: float = Field(default=3.5, ge=3.0, le=4.0)
    state_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    system_mode: SystemMode = SystemMode.NORMAL
    is_initialized: bool = False
    is_shutting_down: bool = False
    fencing: FencingTokenState = Field(default_factory=FencingTokenState)
    telemetry: TelemetryState = Field(default_factory=TelemetryState)
    gpu: GPUState = Field(default_factory=GPUState)
    safety: SafetyState = Field(default_factory=SafetyState)
    memory: MemoryState = Field(default_factory=MemoryState)
    audit: AuditState = Field(default_factory=AuditState)
    current_node: str = "idle"
    retry_count: int = Field(default=0, ge=0, le=10)
    max_retries: int = Field(default=3, ge=0, le=10)
    recursion_depth: int = Field(default=0, ge=0, le=100)
    context_tokens_used: int = Field(default=0, ge=0)
    context_tokens_max: int = Field(default=8192, ge=512, le=131072)
    active_prompt_version: str = "3.5.0"
    node_data: dict[str, Any] = Field(default_factory=dict)
    error_log: list[dict[str, Any]] = Field(default_factory=list)
    state_hash: str = ""
    parent_state_id: Optional[str] = None

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
        "str_strip_whitespace": True,
    }

    @field_validator("fencing")
    @classmethod
    def validate_fencing_token_state(cls, v: FencingTokenState) -> FencingTokenState:
        if v.strict_monotonicity and v.current_token <= v.last_accepted_token:
            if v.reject_equal_tokens:
                raise ValueError(f"Invalid fencing token state: {v.current_token} <= {v.last_accepted_token}")
        return v

    @model_validator(mode="after")
    def validate_state_consistency(self) -> "SystemState":
        self.updated_at = datetime.now(timezone.utc)
        if self.retry_count > self.max_retries:
            raise ValueError(f"Retry count {self.retry_count} exceeds maximum {self.max_retries}")
        if self.context_tokens_used > self.context_tokens_max:
            raise ValueError(f"Context tokens {self.context_tokens_used} exceeds maximum {self.context_tokens_max}")
        self._update_safety_status()
        self._update_state_hash()
        return self

    def _update_safety_status(self) -> None:
        if self.gpu.thermal_state == ThermalState.EMERGENCY:
            self.safety.status = SafetyStatus.EMERGENCY
        elif self.gpu.thermal_state == ThermalState.CRITICAL:
            self.safety.status = SafetyStatus.CRITICAL
        elif self.gpu.thermal_state == ThermalState.WARNING:
            self.safety.status = SafetyStatus.WARNING
        elif not self.safety.heartbeat_active or not self.safety.uart_connected:
            self.safety.status = SafetyStatus.CRITICAL
        else:
            self.safety.status = SafetyStatus.SAFE

    def _update_state_hash(self) -> None:
        state_dict = self.model_dump(exclude={"state_hash", "updated_at"})
        state_json = json.dumps(state_dict, sort_keys=True, default=str)
        self.state_hash = hashlib.sha256(state_json.encode()).hexdigest()

    @property
    def reactive_mode(self) -> bool:
        """
        True when long-term memory (Qdrant) is unavailable.
        Per spec test 10.2: system enters pure reactive mode on warm-start
        recovery when the vector store cannot be reached.
        """
        return not self.memory.qdrant_available

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style accessor for LangGraph / legacy checkpoint compatibility."""
        if hasattr(self, key):
            value = getattr(self, key)
            if isinstance(value, Enum):
                return value.value
            return value
        return self.model_dump().get(key, default)

    def generate_fencing_token(self) -> int:
        return self.fencing.generate_next_token()

    def validate_command_token(self, token: int) -> bool:
        return self.fencing.validate_incoming_token(token)

    def record_error(self, error_type: str, message: str, node: str = "") -> None:
        self.error_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": error_type,
            "message": message,
            "node": node or self.current_node,
        })
        if len(self.error_log) > 100:
            self.error_log = self.error_log[-100:]

    def increment_retry(self) -> bool:
        self.retry_count += 1
        return self.retry_count <= self.max_retries

    def transition_to_mode(self, new_mode: SystemMode) -> None:
        old_mode = self.system_mode
        self.system_mode = new_mode
        self.record_error("MODE_TRANSITION", f"Mode changed from {old_mode} to {new_mode}", "state_manager")

    def to_checkpoint(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any]) -> "SystemState":
        return cls(**data)


def create_initial_state(session_id: Optional[str] = None, initial_mode: SystemMode = SystemMode.NORMAL) -> SystemState:
    return SystemState(session_id=session_id or str(uuid.uuid4()), system_mode=initial_mode, is_initialized=True)


def create_warm_start_state() -> SystemState:
    return SystemState(
        system_mode=SystemMode.WARM_START_REACTIVE,
        is_initialized=True,
        memory=MemoryState(qdrant_available=False, qdrant_collection_loaded=False),
    )


def create_emergency_state() -> SystemState:
    return SystemState(
        system_mode=SystemMode.EMERGENCY_RTL,
        is_initialized=True,
        safety=SafetyState(status=SafetyStatus.EMERGENCY, rtl_triggered=True, emergency_land_pending=True),
    )
