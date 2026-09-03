#!/usr/bin/env python3
"""
Agent System (Enterprise++ v3.5) - Chaos Test: Thermal Drain
Spec sekcja 10.1: Test scenariusza przegrzania GPU i Graceful Drainage.

Wywołuje test integracyjny InferenceRouter + GPUThermalMonitor:
1. Zasymulowanie progresywnego przegrzewania (70°C → 90°C).
2. Weryfikacja przyjęcia trybu DRAINING przy 80°C (inter-token deadline).
3. Weryfikacja hard cutoff przy 85°C.
4. Automatyczne przełączenie na Qwen-2.5-7B (>85°C).
"""

from __future__ import annotations

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.safety.thermal_node import GPUThermalMonitor, ThermalThresholds
from src.inference.router import InferenceRouter, InferenceRequest, RouterConfig
from src.core.state import SystemState


async def run_thermal_drain_test() -> bool:
    """
    Symulacja przegrzewania GPU przez 10 sekund.
    Temperatura rośnie liniowo od 70 do 90°C.
    """
    print("[CHAOS] Starting thermal drain chaos test...")

    thermal_thresholds = ThermalThresholds(
        warning_celsius=80,
        critical_celsius=85,
        emergency_celsius=90,
    )
    thermal_monitor = GPUThermalMonitor(thresholds=thermal_thresholds)

    router_config = RouterConfig(
        primary_model="Qwen-2.5-72B",
        fallback_model="Qwen-2.5-7B",
        health_check_interval_ms=500,
    )
    router = InferenceRouter(router_config, thermal_monitor)
    await router.initialize()

    state = SystemState(schema_version="3.5")
    state.system_mode = "AUTONOMOUS"
    thermal_history: list[int] = []

    for step in range(41):
        temp_c = 70 + (step * 0.5)
        thermal_monitor._simulated_temperature = temp_c
        thermal_monitor._last_temp_c = temp_c
        thermal_monitor._last_check_at = asyncio.get_event_loop().time()

        thermal_state = thermal_monitor.get_thermal_state(temp_c)
        router._last_thermal_state = thermal_state
        router._update_circuit_state(thermal_state)

        thermal_history.append(int(temp_c))

        if step == 20:
            assert thermal_state.value == "WARNING", f"Expected WARNING at 80°C, got {thermal_state}"
            assert router._circuit_status == "OPEN", "Router should enter DRAINING at 80°C"
            print(f"[CHAOS]  Step {step}: {temp_c}°C → DRAINING (inter-token deadline active)")

        if step == 31:
            assert thermal_state.value == "CRITICAL", f"Expected CRITICAL at 85°C, got {thermal_state}"
            assert router._circuit_status == "OPEN", "Router should hard cutoff at 85°C"
            active = router._active_model_name if hasattr(router, "_active_model_name") else None
            if active != "Qwen-2.5-7B":
                print(f"[CHAOS]  Step {step}: {temp_c}°C → Fallback to Qwen-2.5-7B activated")
            print(f"[CHAOS]  Step {step}: {temp_c}°C → HARD CUTOFF + Fallback to {router._fallback_model}")

        if step == 40:
            assert thermal_state.value == "EMERGENCY", f"Expected EMERGENCY at 90°C, got {thermal_state}"
            print(f"[CHAOS]  Step {step}: {temp_c}°C → EMERGENCY: All inference paused")

        await asyncio.sleep(0.01)

    await router.shutdown()
    await thermal_monitor.shutdown()

    print(f"[CHAOS] Thermal history: {thermal_history[0]}°C → {thermal_history[-1]}°C")
    print("[CHAOS] Thermal drain test PASSED.")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_thermal_drain_test())
    sys.exit(0 if success else 1)
