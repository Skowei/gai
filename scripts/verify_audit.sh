#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON_CMD="${PYTHON_CMD:-python3}"
CHECKPOINT_PATH="${CHECKPOINT_PATH:-/var/log/agent_audit/checkpoints/}"
LOG_FILE="${LOG_FILE:-/var/log/agent_audit/verify_audit.log}"
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v) VERBOSE=true; shift ;;
        --checkpoint-path) CHECKPOINT_PATH="$2"; shift 2 ;;
        --log-file) LOG_FILE="$2"; shift 2 ;;
        --help|-h) echo "Usage: $0 [--verbose] [--checkpoint-path PATH]"; exit 0 ;;
        *) echo "Unknown option: $1"; exit 2 ;;
    esac
done

log() {
    local level="$1"; shift
    echo "[$(date -Iseconds)] [$level] $*" | tee -a "$LOG_FILE"
}

check_permissions() {
    if [[ ! -d "$CHECKPOINT_PATH" ]]; then
        mkdir -p "$CHECKPOINT_PATH" 2>/dev/null || { log "ERROR" "Cannot create checkpoint dir"; exit 2; }
    fi
}

check_python() {
    if ! command -v "$PYTHON_CMD" &> /dev/null; then
        log "ERROR" "Python not found: $PYTHON_CMD"; exit 2
    fi
}

verify_integrity() {
    log "INFO" "Starting audit integrity verification..."

    local python_script='import sys, os, json, hashlib
from pathlib import Path

def hash_checkpoint(cp):
    data = f"{cp['sequence']}:{cp['root_hash']}:{cp['entry_count']}:{cp['timestamp']}:{cp['prev_checkpoint_hash']}"
    return hashlib.sha256(data.encode()).hexdigest()

checkpoint_path = sys.argv[1] if len(sys.argv) > 1 else "/var/log/agent_audit/checkpoints/"
checkpoint_dir = Path(checkpoint_path)
if not checkpoint_dir.exists():
    print("CHECKPOINT_DIR_MISSING")
    sys.exit(0)

files = sorted(checkpoint_dir.glob("checkpoint_*.json"))
if len(files) < 2:
    print(f"NOT_ENOUGH_CHECKPOINTS:{len(files)}")
    sys.exit(0)

checkpoints = []
for f in files:
    with open(f) as fh:
        checkpoints.append(json.load(fh))

for i in range(1, len(checkpoints)):
    expected = hash_checkpoint(checkpoints[i-1])
    actual = checkpoints[i].get("prev_checkpoint_hash", "")
    if actual != expected:
        print(f"INTEGRITY_VIOLATION:{checkpoints[i]['sequence']}")
        sys.exit(1)

print(f"INTEGRITY_OK:{len(checkpoints)}:{checkpoints[-1]['root_hash']}")
sys.exit(0)'

    local result
    result=$($PYTHON_CMD -c "$python_script" "$CHECKPOINT_PATH" 2>&1)
    local exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        if [[ "$result" == INTEGRITY_OK:* ]]; then
            log "INFO" "Integrity verified: $result"
            echo "[PASS] Audit integrity verified"
            return 0
        elif [[ "$result" == NOT_ENOUGH_CHECKPOINTS:* ]]; then
            log "WARN" "Not enough checkpoints: $result"
            echo "[WARN] Not enough checkpoints"
            return 0
        fi
    elif [[ $exit_code -eq 1 ]]; then
        if [[ "$result" == INTEGRITY_VIOLATION:* ]]; then
            log "CRITICAL" "INTEGRITY VIOLATION: $result"
            echo "[CRITICAL] INTEGRITY VIOLATION - SYSTEM HALT"
            return 1
        fi
    fi

    log "ERROR" "Unexpected result: $result"
    return 2
}

main() {
    log "INFO" "=== Agent System v3.5 - Audit Integrity Check ==="
    check_permissions
    check_python
    verify_integrity
    return $?
}

main "$@"
exit $?
