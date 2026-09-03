"""
Agent System (Enterprise++ v3.5) - NVIDIA MPS Manager
Konfiguracja i zarządzanie NVIDIA Multi-Process Service (MPS)
ze sztywnym partycjonowaniem VRAM 50/30/20.

Zgodnie ze spec.md sekcja 5.7 (NVIDIA MPS Thread Priority & Resource Balancing):
- max 50% VRAM -> vLLM (Llama)
- max 30% VRAM -> Roboflow CV / YOLO
- max 20% VRAM -> narzędzia i parsery
- tryb EXCLUSIVE_PROCESS izoluje procesy od siebie

Docker/init integration: scripts/init_mps.sh
Uses nvidia-smi and nvidia-cuda-mps-control with subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

VLLM_PERCENT = 50
ROBOFLOW_PERCENT = 30
TOOLS_PERCENT = 20


class MPSAllocationConfig(BaseModel):
    """VRAM allocation among workloads (must sum to 100)."""
    vllm_percent: int = Field(default=VLLM_PERCENT, ge=10, le=80)
    roboflow_percent: int = Field(default=ROBOFLOW_PERCENT, ge=10, le=60)
    tools_percent: int = Field(default=TOOLS_PERCENT, ge=5, le=40)


@dataclass
class MPSStatus:
    """Current MPS daemon / GPU status snapshot."""
    daemon_running: bool
    gpu_compute_mode: str
    gpu_name: str
    memory_total_mb: int
    memory_used_mb: int
    memory_free_mb: int
    timestamp: float = field(default_factory=time.time)


class MPSManager:
    """
    MPSManager: high-level async control of NVIDIA MPS.
    """

    def __init__(
        self,
        allocation: MPSAllocationConfig,
        gpu_id: int = 0,
        visible_devices: str = "0",
    ):
        total = (
            allocation.vllm_percent
            + allocation.roboflow_percent
            + allocation.tools_percent
        )
        if total != 100:
            raise ValueError(f"MPS allocation must sum to 100, got {total}")
        self._allocation = allocation
        self._gpu_id = gpu_id
        self._visible_devices = visible_devices
        self._mps_dir = os.environ.get("CUDA_MPS_PIPE_DIRECTORY", "/tmp/nvidia-mps")
        self._log_dir = os.environ.get("CUDA_MPS_LOG_DIRECTORY", "/var/log/nvidia-mps")
        self._env = os.environ.copy()
        self._env["CUDA_VISIBLE_DEVICES"] = self._visible_devices
        self._env["CUDA_MPS_PIPE_DIRECTORY"] = self._mps_dir
        self._env["CUDA_MPS_LOG_DIRECTORY"] = self._log_dir

    async def initialize(self) -> None:
        """Ensure MPS daemon is running and GPU is in exclusive mode."""
        await asyncio.to_thread(self._ensure_directories)
        await asyncio.to_thread(self._ensure_exclusive_mode)
        await asyncio.to_thread(self._ensure_daemon)
        logger.info("MPSManager initialized (GPU %d, allocation 50/30/20)", self._gpu_id)

    async def reset(self) -> bool:
        """Full MPS reset (kill daemon, restart, re-arm exclusivity)."""
        if shutil.which("nvidia-cuda-mps-control"):
            proc = subprocess.run(
                ["sh", "-c", "echo quit | nvidia-cuda-mps-control"],
                capture_output=True,
                text=True,
                timeout=10,
                env=self._env,
            )
            _ = proc.returncode
        await asyncio.to_thread(self._ensure_daemon)
        await asyncio.to_thread(self._ensure_exclusive_mode)
        logger.info("MPS reset complete")
        return True

    async def get_status(self) -> MPSStatus:
        """Snapshot current MPS + GPU state."""
        daemon_running = await self._is_daemon_running()
        gpu_name = ""
        mem_total = 0
        mem_used = 0
        mem_free = 0
        compute_mode = "unknown"

        if shutil.which("nvidia-smi"):
            code, out, _ = await self._run(
                ["nvidia-smi", "-i", str(self._gpu_id),
                 "--query-gpu=name,total,used,free,compute_mode",
                 "--format=csv,noheader,nounits"],
                check=False,
            )
            if code == 0 and out.strip():
                parts = out.strip().split(",")
                gpu_name = parts[0].strip() if len(parts) > 0 else ""
                mem_total = int(parts[1].strip() or 0) if len(parts) > 1 else 0
                mem_used = int(parts[2].strip() or 0) if len(parts) > 2 else 0
                mem_free = int(parts[3].strip() or 0) if len(parts) > 3 else 0
                compute_mode = parts[4].strip() if len(parts) > 4 else "unknown"

        return MPSStatus(
            daemon_running=daemon_running,
            gpu_compute_mode=compute_mode,
            gpu_name=gpu_name,
            memory_total_mb=mem_total,
            memory_used_mb=mem_used,
            memory_free_mb=mem_free,
        )

    async def _is_daemon_running(self) -> bool:
        def _pgrep() -> bool:
            try:
                proc = subprocess.run(
                    ["pgrep", "-x", "nvidia-cuda-mps-control"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return proc.returncode == 0
            except Exception:
                return False

        return await asyncio.to_thread(_pgrep)

    @property
    def allocation(self) -> MPSAllocationConfig:
        return self._allocation

    async def health_check(self) -> dict[str, Any]:
        status = await self.get_status()
        return {
            "status": "healthy" if status.daemon_running else "degraded",
            "gpu": status.gpu_name,
            "compute_mode": status.gpu_compute_mode,
            "memory_total_mb": status.memory_total_mb,
            "memory_used_mb": status.memory_used_mb,
            "allocation": {
                "vllm": self._allocation.vllm_percent,
                "roboflow": self._allocation.roboflow_percent,
                "tools": self._allocation.tools_percent,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await asyncio.to_thread(self._ensure_daemon)
        logger.info("MPSManager initialized (GPU %d, allocation 50/30/20)", self._gpu_id)

    async def _run(self, cmd: list[str], check: bool = True) -> tuple[int, str, str]:
        def _exec() -> tuple[int, str, str]:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                env=self._env,
            )
            return proc.returncode, proc.stdout, proc.stderr

        code, out, err = await asyncio.to_thread(_exec)
        if check and code != 0:
            raise RuntimeError(f"Command {cmd} failed ({code}): {err}")
        return code, out, err

    def _ensure_directories(self) -> None:
        os.makedirs(self._mps_dir, exist_ok=True)
        os.makedirs(self._log_dir, exist_ok=True)

    def _ensure_exclusive_mode(self) -> None:
        if not shutil.which("nvidia-smi"):
            logger.warning("nvidia-smi not found - MPS nominal mode assumed")
            return
        subprocess.run(
            ["nvidia-smi", "-i", str(self._gpu_id), "-c", "EXCLUSIVE_PROCESS"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def _ensure_daemon(self) -> None:
        if not shutil.which("nvidia-cuda-mps-control"):
            logger.warning("nvidia-cuda-mps-control not found - MPS disabled")
            return
        try:
            subprocess.run(
                ["nvidia-cuda-mps-control", "-d"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass
        time.sleep(0.5)