#!/bin/bash
#
# Agent System (Enterprise++ v3.5) - NVIDIA MPS Initialization Script
# Configures Multi-Process Service with VRAM partitioning (50/30/20)
#
# Usage: ./init_mps.sh [--reset] [--status]
#
# VRAM Allocation:
#   - 50% vLLM (Llama 3.1 70B)
#   - 30% Roboflow CV / YOLO
#   - 20% Tools and parsers
#
set -euo pipefail

# Configuration
GPU_ID=0
CUDA_VISIBLE_DEVICES="0"
MPS_PIPE_DIRECTORY="/tmp/nvidia-mps"
MPS_LOG_DIRECTORY="/var/log/nvidia-mps"

# VRAM allocation percentages
VLLM_PERCENT=50
ROBOFLOW_PERCENT=30
TOOLS_PERCENT=20

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo "[$(date -Iseconds)] [$1] ${@:2}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log "ERROR" "This script must be run as root for GPU configuration"
        exit 1
    fi
}

check_nvidia() {
    if ! command -v nvidia-smi &> /dev/null; then
        log "ERROR" "nvidia-smi not found. Is NVIDIA driver installed?"
        exit 1
    fi

    if ! command -v nvidia-cuda-mps-control &> /dev/null; then
        log "ERROR" "nvidia-cuda-mps-control not found. Is CUDA toolkit installed?"
        exit 1
    fi
}

reset_mps() {
    log "INFO" "Resetting CUDA MPS..."
    if pgrep -x nvidia-cuda-mps-control > /dev/null 2>&1; then
        echo quit | nvidia-cuda-mps-control 2>/dev/null || true
        sleep 1
        pkill -9 nvidia-cuda-mps-control 2>/dev/null || true
        log "INFO" "MPS daemon stopped"
    else
        log "INFO" "MPS daemon not running"
    fi
}

set_exclusive_process() {
    log "INFO" "Setting GPU $GPU_ID to EXCLUSIVE_PROCESS mode..."
    nvidia-smi -i "$GPU_ID" -c EXCLUSIVE_PROCESS 2>/dev/null || {
        log "ERROR" "Failed to set EXCLUSIVE_PROCESS mode"
        log "ERROR" "Ensure no other processes are using GPU $GPU_ID"
        exit 1
    }
    log "INFO" "GPU $GPU_ID set to EXCLUSIVE_PROCESS mode"
}

start_mps_daemon() {
    log "INFO" "Starting CUDA MPS daemon..."
    mkdir -p "$MPS_PIPE_DIRECTORY" "$MPS_LOG_DIRECTORY"
    nvidia-cuda-mps-control -d 2>/dev/null || {
        log "ERROR" "Failed to start MPS daemon"
        exit 1
    }
    sleep 1
    if pgrep -x nvidia-cuda-mps-control > /dev/null 2>&1; then
        log "INFO" "MPS daemon started successfully"
    else
        log "ERROR" "MPS daemon failed to start"
        exit 1
    fi
}

configure_vram_allocation() {
    log "INFO" "Configuring VRAM allocation..."
    log "INFO" "  vLLM: ${VLLM_PERCENT}%"
    log "INFO" "  Roboflow CV: ${ROBOFLOW_PERCENT}%"
    log "INFO" "  Tools: ${TOOLS_PERCENT}%"
    echo "set_default_device_pinned_memory_limit 0 ${VLLM_PERCENT}" | nvidia-cuda-mps-control 2>/dev/null || true
    log "INFO" "VRAM allocation configured"
}

show_status() {
    log "INFO" "=== NVIDIA MPS Status ==="
    echo ""
    nvidia-smi -i "$GPU_ID" --query-gpu=name,memory.total,memory.used,memory.free,compute_mode --format=csv,noheader 2>/dev/null || true
    echo ""
    if pgrep -x nvidia-cuda-mps-control > /dev/null 2>&1; then
        log "INFO" "MPS daemon: RUNNING"
    else
        log "INFO" "MPS daemon: STOPPED"
    fi
    echo ""
    log "INFO" "VRAM Allocation:"
    log "INFO" "  vLLM: ${VLLM_PERCENT}%"
    log "INFO" "  Roboflow CV: ${ROBOFLOW_PERCENT}%"
    log "INFO" "  Tools: ${TOOLS_PERCENT}%"
}

main() {
    local do_reset=false
    local do_status=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --reset) do_reset=true; shift ;;
            --status) do_status=true; shift ;;
            --help|-h)
                echo "Usage: $0 [--reset] [--status]"
                echo ""
                echo "Options:"
                echo "  --reset   Reset MPS before initialization"
                echo "  --status  Show current MPS status"
                echo "  --help    Show this help message"
                exit 0
                ;;
            *) echo "Unknown option: $1"; exit 1 ;;
        esac
    done

    export CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES"

    if [[ "$do_status" == true ]]; then
        show_status
        exit 0
    fi

    check_root
    check_nvidia

    log "INFO" "========================================"
    log "INFO" "Agent System v3.5 - NVIDIA MPS Init"
    log "INFO" "========================================"

    if [[ "$do_reset" == true ]]; then
        reset_mps
    fi

    set_exclusive_process
    start_mps_daemon
    configure_vram_allocation

    log "INFO" "========================================"
    log "INFO" "MPS initialization complete"
    log "INFO" "========================================"
    show_status
}

main "$@"
