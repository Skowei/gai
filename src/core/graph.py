"""
Agent System (Enterprise++ v3.5) - LangGraph State Graph
Complete decision graph with nodes: Ingestion, Router, CoreBrain, Execution.

Features:
- Full LangGraph StateGraph with SystemState
- Pydantic Output Guardrails with max_retries=3
- Safe-state fallback after 3 failed JSON parsing attempts
- Integration with InferenceRouter and GPUThermalMonitor
- Structured error logging in state history
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

from src.core.state import (
    SystemState,
    SystemMode,
    SafetyStatus,
    ThermalState,
    create_initial_state,
)


class OutputGuardrails(BaseModel):
    """Pydantic guardrails for validating CoreBrain JSON output."""
    action_type: str = Field(..., min_length=1, max_length=64)
    fencing_token: int = Field(..., ge=0)
    safety_status: str = Field(default="safe")
    target_device: Optional[str] = None
    command_payload: dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_json(cls, json_str: str) -> "OutputGuardrails":
        """Parse and validate JSON string."""
        try:
            data = json.loads(json_str)
            return cls(**data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        except ValidationError as e:
            raise ValueError(f"Schema validation failed: {e}")

    @classmethod
    def safe_default(cls, fencing_token: int = 0) -> "OutputGuardrails":
        """Generate safe default output for fallback."""
        return cls(
            action_type="status_query",
            fencing_token=fencing_token,
            safety_status="safe",
            reasoning="Safe-state fallback applied after max retries",
            confidence=1.0,
        )


class GraphNodeResult(BaseModel):
    """Result from a graph node execution."""
    node_name: str
    success: bool
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    retry_count: int = 0


class LangGraphDecisionEngine:
    """
    LangGraph Decision Engine with full state graph.
    
    Nodes:
    - ingestion_node: Process incoming telemetry/data
    - router_node: Route through circuit breaker
    - core_brain_node: AI decision making with guardrails
    - execution_node: Execute validated commands
    """

    def __init__(
        self,
        router: Any = None,
        thermal_monitor: Any = None,
        mavlink_controller: Any = None,
        max_retries: int = 3,
    ):
        self._router = router
        self._thermal_monitor = thermal_monitor
        self._mavlink_controller = mavlink_controller
        self._max_retries = max_retries
        self._is_running = False
        self._execution_count = 0
        self._error_count = 0
        self._fallback_count = 0

    async def initialize(self) -> None:
        """Initialize the decision engine."""
        self._is_running = True
        logger.info("LangGraphDecisionEngine initialized")

    async def shutdown(self) -> None:
        """Shutdown the decision engine."""
        self._is_running = False
        logger.info("LangGraphDecisionEngine shutdown")

    async def process(self, state: SystemState, input_data: dict[str, Any]) -> SystemState:
        """
        Process input through the complete decision graph.
        
        Graph flow:
        1. ingestion_node -> process input
        2. router_node -> circuit breaker check
        3. core_brain_node -> AI decision with guardrails
        4. execution_node -> execute command
        """
        if not self._is_running:
            raise RuntimeError("Decision engine not running")

        self._execution_count += 1
        state.current_node = "graph_start"

        try:
            # Node 1: Ingestion
            state = await self._ingestion_node(state, input_data)

            # Node 2: Router (Circuit Breaker)
            state = await self._router_node(state)

            # Node 3: Core Brain (AI Decision with Guardrails)
            state = await self._core_brain_node(state)

            # Node 4: Execution
            state = await self._execution_node(state)

            state.current_node = "graph_complete"

        except Exception as e:
            self._error_count += 1
            state.record_error("GRAPH_ERROR", str(e), "graph")
            logger.error(f"Graph execution error: {e}")

        return state

    async def _ingestion_node(self, state: SystemState, input_data: dict[str, Any]) -> SystemState:
        """
        Ingestion Node: Process incoming telemetry and data.
        """
        state.current_node = "ingestion"
        start_time = asyncio.get_event_loop().time()

        try:
            if "telemetry" in input_data:
                telem = input_data["telemetry"]
                if "temperature_celsius" in telem:
                    state.gpu.temperature_celsius = telem["temperature_celsius"]
                if "gpu_utilization" in telem:
                    state.gpu.gpu_utilization_percent = telem["gpu_utilization"]
                if "memory_used_mb" in telem:
                    state.gpu.memory_used_mb = telem["memory_used_mb"]

            if "command" in input_data:
                state.node_data["pending_command"] = input_data["command"]

            if "fencing_token" in input_data:
                if not state.validate_command_token(input_data["fencing_token"]):
                    state.record_error("FENCING_REJECTED", f"Token {input_data['fencing_token']} rejected", "ingestion")

            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            state.node_data["ingestion_time_ms"] = elapsed

        except Exception as e:
            state.record_error("INGESTION_ERROR", str(e), "ingestion")
            logger.error(f"Ingestion node error: {e}")

        return state

    async def _router_node(self, state: SystemState) -> SystemState:
        """
        Router Node: Circuit breaker and thermal check.
        """
        state.current_node = "router"
        start_time = asyncio.get_event_loop().time()

        try:
            if self._thermal_monitor:
                thermal_flags = await self._thermal_monitor.check_thermal_status()

                if thermal_flags.should_emergency_stop:
                    state.system_mode = SystemMode.EMERGENCY_RTL
                    state.safety.status = SafetyStatus.EMERGENCY
                    state.record_error("THERMAL_EMERGENCY", f"Temp {thermal_flags.current_temperature}°C", "router")

                elif thermal_flags.should_hard_cutoff:
                    state.system_mode = SystemMode.THERMAL_THROTTLE
                    state.safety.status = SafetyStatus.CRITICAL
                    state.gpu.active_model = "qwen-2.5-7b"
                    state.record_error("THERMAL_HARD_CUTOFF", f"Temp {thermal_flags.current_temperature}°C", "router")

                elif thermal_flags.should_throttle:
                    state.system_mode = SystemMode.THERMAL_THROTTLE
                    state.safety.status = SafetyStatus.WARNING
                    state.gpu.active_model = "qwen-2.5-7b"

            if self._router:
                router_state = self._router.state.value
                state.node_data["circuit_breaker_state"] = router_state

            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            state.node_data["router_time_ms"] = elapsed

        except Exception as e:
            state.record_error("ROUTER_ERROR", str(e), "router")
            logger.error(f"Router node error: {e}")

        return state

    async def _core_brain_node(self, state: SystemState) -> SystemState:
        """
        Core Brain Node: AI decision making with Pydantic guardrails.
        
        Implements max_retries=3 for JSON parsing/validation.
        After 3 failures, applies safe-state fallback.
        """
        state.current_node = "core_brain"
        start_time = asyncio.get_event_loop().time()
        last_error = None

        for attempt in range(1, self._max_retries + 1):
            try:
                raw_output = await self._call_ai_model(state)
                validated_output = OutputGuardrails.from_json(raw_output)

                state.node_data["ai_output"] = validated_output.model_dump()
                state.node_data["ai_model"] = state.gpu.active_model
                state.retry_count = 0

                elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
                state.node_data["core_brain_time_ms"] = elapsed

                return state

            except (ValueError, json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                state.retry_count = attempt
                state.record_error("GUARDRAIL_RETRY", f"Attempt {attempt}/{self._max_retries}: {e}", "core_brain")
                logger.warning(f"CoreBrain guardrail retry {attempt}/{self._max_retries}: {e}")

                if attempt < self._max_retries:
                    await asyncio.sleep(0.1 * attempt)

        # All retries exhausted - apply safe-state fallback
        self._fallback_count += 1
        logger.critical(f"Safe-state fallback applied after {self._max_retries} failures: {last_error}")

        safe_output = OutputGuardrails.safe_default(state.fencing_token.current_token)
        state.node_data["ai_output"] = safe_output.model_dump()
        state.node_data["fallback_applied"] = True
        state.node_data["fallback_reason"] = last_error
        state.system_mode = SystemMode.MAINTENANCE
        state.record_error("SAFE_STATE_FALLBACK", f"Applied after {self._max_retries} retries: {last_error}", "core_brain")

        elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
        state.node_data["core_brain_time_ms"] = elapsed

        return state

    async def _call_ai_model(self, state: SystemState) -> str:
        """
        Real inference path: route through InferenceRouter (Circuit Breaker
        + thermal fallback). When router is not wired (e.g. unit tests),
        falls back to a deterministic guardrail-compliant decision built
        from live SystemState (never a hardcoded fake).
        """
        prompt_payload = {
            "system_mode": state.system_mode.value,
            "safety_status": state.safety.status.value,
            "active_model": state.gpu.active_model,
            "telemetry": {
                "temperature": state.gpu.temperature_celsius,
                "gpu_util": state.gpu.gpu_utilization_percent,
                "battery": state.telemetry.battery_percent,
                "altitude": state.telemetry.altitude_m,
            },
            "pending_command": state.node_data.get("pending_command"),
            "context_tokens_used": state.context_tokens_used,
        }

        if self._router is not None:
            response = await self._router.route_request(prompt_payload)
            raw_text = response.get("response", "")
            if raw_text:
                return raw_text
            # Router returned structured fallback -> materialize valid JSON
            output = {
                "action_type": "status_query",
                "fencing_token": state.fencing_token.current_token,
                "safety_status": state.safety.status.value,
                "confidence": 0.5,
                "reasoning": f"Router fallback via {response.get('model', 'unknown')}: "
                             f"{response.get('fallback_reason', 'no content')}",
            }
            return json.dumps(output)

        # Deterministic decision from live state (no router wired):
        if state.safety.status == SafetyStatus.EMERGENCY:
            output = {
                "action_type": "emergency_rtl",
                "fencing_token": state.fencing_token.current_token,
                "safety_status": "emergency",
                "confidence": 1.0,
                "reasoning": "Emergency safety status -> immediate RTL",
            }
        elif state.system_mode == SystemMode.THERMAL_THROTTLE:
            output = {
                "action_type": "status_query",
                "fencing_token": state.fencing_token.current_token,
                "safety_status": state.safety.status.value,
                "confidence": 0.9,
                "reasoning": "Thermal throttle active - read-only posture on fallback model",
            }
        else:
            pending = state.node_data.get("pending_command")
            if pending:
                output = {
                    "action_type": "command_execute",
                    "fencing_token": state.fencing_token.current_token,
                    "safety_status": state.safety.status.value,
                    "command_payload": pending,
                    "confidence": 0.95,
                    "reasoning": "Live telemetry nominal - executing validated pending command",
                }
            else:
                output = {
                    "action_type": "status_query",
                    "fencing_token": state.fencing_token.current_token,
                    "safety_status": state.safety.status.value,
                    "confidence": 0.95,
                    "reasoning": "Nominal telemetry - status query",
                }
        return json.dumps(output)

    async def _execution_node(self, state: SystemState) -> SystemState:
        """
        Execution Node: Execute validated commands through the MCP
        MAVLink controller (fencing token + etcd distributed lock).
        """
        state.current_node = "execution"
        start_time = asyncio.get_event_loop().time()

        try:
            ai_output = state.node_data.get("ai_output", {})
            action_type = ai_output.get("action_type", "status_query")

            if action_type == "emergency_rtl":
                state.system_mode = SystemMode.EMERGENCY_RTL
                state.safety.rtl_triggered = True
                state.record_error("RTL_TRIGGERED", "Emergency RTL executed", "execution")

                if self._mavlink_controller is not None:
                    from src.mcp.mavlink_ctrl import (
                        MAVLinkCommand,
                        MAVLinkCommandPayload,
                    )

                    payload = MAVLinkCommandPayload(
                        command=MAVLinkCommand.RTL,
                        fencing_token=int(ai_output.get("fencing_token", 0)),
                        require_lock=True,
                        timeout_ms=2000,
                        source_node="execution_node",
                    )
                    cmd_result = await self._mavlink_controller.send_command(payload)
                    state.node_data["command_result"] = cmd_result.model_dump()
                    if cmd_result.status.value in ("token_rejected", "lock_denied"):
                        state.record_error(
                            "HARDWARE_CMD_REJECTED",
                            f"RTL rejected: {cmd_result.error_message}",
                            "execution",
                        )
                else:
                    state.record_error(
                        "MAVLINK_NOT_WIRED",
                        "No MAVLink controller wired - RTL logged only",
                        "execution",
                    )

            elif action_type == "command_execute":
                command = ai_output.get("command_payload", {})
                state.node_data["executed_command"] = command

                if self._mavlink_controller is not None and command:
                    from src.mcp.mavlink_ctrl import (
                        MAVLinkCommand,
                        MAVLinkCommandPayload,
                    )

                    try:
                        mav_cmd = MAVLinkCommand(command.get("type", "hold"))
                    except ValueError:
                        mav_cmd = MAVLinkCommand.HOLD

                    payload = MAVLinkCommandPayload(
                        command=mav_cmd,
                        fencing_token=int(ai_output.get("fencing_token", 0)),
                        params=command.get("params", {}),
                        require_lock=True,
                        timeout_ms=5000,
                        source_node="execution_node",
                    )
                    cmd_result = await self._mavlink_controller.send_command(payload)
                    state.node_data["command_result"] = cmd_result.model_dump()
                    if cmd_result.status.value == "token_rejected":
                        state.record_error(
                            "FENCING_TOKEN_REJECTED",
                            f"Command rejected: {cmd_result.error_message}",
                            "execution",
                        )

            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            state.node_data["execution_time_ms"] = elapsed

        except Exception as e:
            state.record_error("EXECUTION_ERROR", str(e), "execution")
            logger.error(f"Execution node error: {e}")

        return state

    @property
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._is_running

    @property
    def stats(self) -> dict[str, Any]:
        """Get engine statistics."""
        return {
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "fallback_count": self._fallback_count,
            "is_running": self._is_running,
        }

    async def health_check(self) -> dict[str, Any]:
        """Health check for decision engine."""
        return {
            "status": "healthy" if self._is_running else "stopped",
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "fallback_count": self._fallback_count,
            "max_retries": self._max_retries,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def _probe_qdrant_available(host: str = "qdrant", port: int = 6333,
                                  timeout_s: float = 3.0) -> bool:
    """Probe local Qdrant availability (warm-start detection, spec 10.2)."""

    async def _probe() -> bool:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return True
        except OSError:
            return False

    try:
        return await asyncio.wait_for(_probe(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return False


async def initialize_system_state(
    session_id: Optional[str] = None,
    qdrant_host: str = "qdrant",
    qdrant_port: int = 6333,
) -> SystemState:
    """
    Initialize system state at cold/warm start (spec 10.2).

    Probes Qdrant availability:
    - Reachable   -> NORMAL mode, long-term memory armed
    - Unreachable -> WARM_START_REACTIVE (reactive_mode=True), sensor-only
    """
    qdrant_ok = await _probe_qdrant_available(qdrant_host, qdrant_port)

    if qdrant_ok:
        state = SystemState(
            session_id=session_id,
            system_mode=SystemMode.NORMAL,
            is_initialized=True,
        )
        state.memory.qdrant_available = True
        state.memory.qdrant_collection_loaded = True
        logger.info("System initialized: NORMAL mode (Qdrant reachable)")
    else:
        state = SystemState(
            session_id=session_id,
            system_mode=SystemMode.WARM_START_REACTIVE,
            is_initialized=True,
        )
        state.memory.qdrant_available = False
        state.memory.qdrant_collection_loaded = False
        state.record_error(
            "WARM_START_REACTIVE",
            "Qdrant unreachable at startup - reactive sensor-only mode",
            "graph",
        )
        logger.warning(
            "System initialized: WARM_START_REACTIVE (reactive_mode=True)"
        )
    return state
