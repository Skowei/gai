"""
Agent System (Enterprise++ v3.5) - State Migrators
Handles migration of state structures from v1 and v2 to v3.5.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import ValidationError

from src.core.state import (
    SystemState, SystemMode, ThermalState, InferenceModel, SafetyStatus,
    FencingTokenState, TelemetryState, GPUState, SafetyState, MemoryState, AuditState,
)

logger = logging.getLogger(__name__)

_MIGRATIONS: dict[tuple[float, float], Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_migration(from_version: float, to_version: float):
    def decorator(func: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        _MIGRATIONS[(from_version, to_version)] = func
        return func
    return decorator


def get_migration_path(from_version: float, to_version: float = 3.5) -> list[tuple[float, float]]:
    if from_version == to_version:
        return []
    paths = {
        (1.0, 3.5): [(1.0, 2.0), (2.0, 3.5)],
        (2.0, 3.5): [(2.0, 3.5)],
        (1.0, 2.0): [(1.0, 2.0)],
        (3.0, 3.5): [(3.0, 3.5)],
    }
    if (from_version, to_version) in paths:
        return paths[(from_version, to_version)]
    for mid_version in [2.0, 3.0]:
        if from_version < mid_version < to_version:
            first_leg = get_migration_path(from_version, mid_version)
            second_leg = get_migration_path(mid_version, to_version)
            if first_leg and second_leg:
                return first_leg + second_leg
    raise ValueError(f"No migration path from v{from_version} to v{to_version}")


@register_migration(1.0, 2.0)
def migrate_v1_to_v2(state: dict[str, Any]) -> dict[str, Any]:
    logger.info("Migrating state from v1.0 to v2.0")
    migrated = copy.deepcopy(state)
    migrated["schema_version"] = 2.0
    if "fencing_token" in migrated and "fencing" not in migrated:
        old_token = migrated.pop("fencing_token", 1000)
        migrated["fencing"] = {
            "current_token": old_token,
            "last_accepted_token": old_token - 1,
            "token_increment": 1,
            "max_token_value": 999999999,
            "strict_monotonicity": True,
            "reject_equal_tokens": True,
            "reject_stale_threshold_ms": 1000,
            "last_token_timestamp": datetime.now(timezone.utc).timestamp(),
            "token_history_hash": "",
        }
    if "telemetry" in migrated:
        telemetry = migrated["telemetry"]
        telemetry.setdefault("vibration_x", 0.0)
        telemetry.setdefault("vibration_y", 0.0)
        telemetry.setdefault("vibration_z", 0.0)
        telemetry.setdefault("is_armed", False)
        telemetry.setdefault("flight_mode", "UNKNOWN")
    if "gpu" in migrated:
        gpu = migrated["gpu"]
        gpu.setdefault("thermal_state", ThermalState.NOMINAL.value)
        gpu.setdefault("active_model", InferenceModel.PRIMARY.value)
        gpu.setdefault("mps_enabled", True)
        gpu.setdefault("vram_allocation", {"vllm": 50, "roboflow": 30, "tools": 20})
    if "mode" in migrated and "system_mode" not in migrated:
        old_mode = migrated.pop("mode", "normal")
        mode_mapping = {
            "normal": SystemMode.NORMAL.value,
            "safe": SystemMode.MAINTENANCE.value,
            "emergency": SystemMode.EMERGENCY_RTL.value,
        }
        migrated["system_mode"] = mode_mapping.get(old_mode, SystemMode.NORMAL.value)
    if "audit" not in migrated:
        migrated["audit"] = {
            "merkle_root_hash": "",
            "total_entries": 0,
            "last_flush_timestamp": 0.0,
            "ring_buffer_usage": 0.0,
            "integrity_verified": True,
            "last_verification_timestamp": 0.0,
        }
    if "memory" not in migrated:
        migrated["memory"] = {
            "qdrant_available": False,
            "qdrant_collection_loaded": False,
            "total_vectors": 0,
            "last_query_timestamp": 0.0,
            "cache_hit_rate": 0.0,
            "semantic_cache_entries": 0,
        }
    return migrated


@register_migration(2.0, 3.5)
def migrate_v2_to_v35(state: dict[str, Any]) -> dict[str, Any]:
    logger.info("Migrating state from v2.0 to v3.5")
    migrated = copy.deepcopy(state)
    migrated["schema_version"] = 3.5
    migrated.setdefault("parent_state_id", None)
    migrated.setdefault("state_hash", "")
    migrated.setdefault("error_log", [])
    migrated.setdefault("node_data", {})
    if "fencing" in migrated:
        fencing = migrated["fencing"]
        fencing.setdefault("token_history_hash", "")
        fencing.setdefault("last_token_timestamp", datetime.now(timezone.utc).timestamp())
    if "safety" in migrated:
        safety = migrated["safety"]
        safety.setdefault("gps_spoofing_detected", False)
        safety.setdefault("geofence_breached", False)
        safety.setdefault("rtl_triggered", False)
        safety.setdefault("emergency_land_pending", False)
    migrated.setdefault("context_tokens_used", 0)
    migrated.setdefault("context_tokens_max", 8192)
    migrated.setdefault("active_prompt_version", "3.5.0")
    migrated.setdefault("recursion_depth", 0)
    migrated.setdefault("max_retries", 3)
    return migrated


@register_migration(3.0, 3.5)
def migrate_v3_to_v35(state: dict[str, Any]) -> dict[str, Any]:
    logger.info("Migrating state from v3.0 to v3.5")
    migrated = copy.deepcopy(state)
    migrated["schema_version"] = 3.5
    migrated.setdefault("parent_state_id", None)
    migrated.setdefault("error_log", [])
    migrated.setdefault("node_data", {})
    return migrated


def detect_schema_version(state: dict[str, Any]) -> float:
    version = state.get("schema_version", state.get("version", 1.0))
    try:
        return float(version)
    except (TypeError, ValueError):
        return 1.0


def migrate_state(state: dict[str, Any], target_version: float = 3.5, validate: bool = True) -> SystemState:
    source_version = detect_schema_version(state)
    logger.info(f"Starting migration from v{source_version} to v{target_version}")
    if source_version == target_version:
        if validate:
            return SystemState(**state)
        return state
    migration_path = get_migration_path(source_version, target_version)
    migrated_state = copy.deepcopy(state)
    for from_ver, to_ver in migration_path:
        migration_func = _MIGRATIONS.get((from_ver, to_ver))
        if migration_func is None:
            raise ValueError(f"No migration function for v{from_ver} to v{to_ver}")
        migrated_state = migration_func(migrated_state)
        migrated_state["schema_version"] = to_ver
    if validate:
        try:
            return SystemState(**migrated_state)
        except ValidationError as e:
            logger.error(f"Migration validation failed: {e}")
            raise
    return migrated_state


def migrate_v1_to_v3(state: dict[str, Any]) -> SystemState:
    return migrate_state(state, target_version=3.5)


def migrate_v2_to_v3(state: dict[str, Any]) -> SystemState:
    return migrate_state(state, target_version=3.5)


def create_migration_report(original_state: dict[str, Any], migrated_state: SystemState) -> dict[str, Any]:
    original_version = detect_schema_version(original_state)
    return {
        "source_version": original_version,
        "target_version": 3.5,
        "migration_timestamp": datetime.now(timezone.utc).isoformat(),
        "state_id": migrated_state.state_id,
        "session_id": migrated_state.session_id,
    }


def validate_migration_compatibility(state: dict[str, Any]) -> dict[str, Any]:
    version = detect_schema_version(state)
    issues = []
    warnings = []
    if version <= 1.0:
        if "fencing_token" not in state and "fencing" not in state:
            issues.append("Missing fencing token data")
        if "telemetry" not in state:
            warnings.append("Missing telemetry state")
    if version <= 2.0:
        if "audit" not in state:
            warnings.append("Missing audit state (will be created)")
        if "memory" not in state:
            warnings.append("Missing memory state (will be created)")
    return {"compatible": len(issues) == 0, "source_version": version, "issues": issues, "warnings": warnings}
