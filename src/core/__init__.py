"""
Agent System (Enterprise++ v3.5) - Core Module
Central brain and state management for the autonomous control system.
"""

from src.core.state import (
    SystemState,
    FencingTokenState,
    TelemetryState,
    GPUState,
    SafetyState,
    MemoryState,
    AuditState,
    SystemMode,
    SafetyStatus,
    ThermalState,
    InferenceModel,
    create_initial_state,
    create_warm_start_state,
    create_emergency_state,
)
from src.core.migrators import (
    migrate_state,
    migrate_v1_to_v3,
    migrate_v2_to_v3,
    detect_schema_version,
    create_migration_report,
    validate_migration_compatibility,
)

__all__ = [
    "SystemState",
    "FencingTokenState",
    "TelemetryState",
    "GPUState",
    "SafetyState",
    "MemoryState",
    "AuditState",
    "SystemMode",
    "SafetyStatus",
    "ThermalState",
    "InferenceModel",
    "create_initial_state",
    "create_warm_start_state",
    "create_emergency_state",
    "migrate_state",
    "migrate_v1_to_v3",
    "migrate_v2_to_v3",
    "detect_schema_version",
    "create_migration_report",
    "validate_migration_compatibility",
]
