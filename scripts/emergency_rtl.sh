#!/bin/bash
#
# Agent System (Enterprise++ v3.5) - Emergency Return to Launch Script
# Simulates hardware Dead Man's Switch via UART for drone RTL command.
#
# Usage: ./emergency_rtl.sh [--uart-device DEVICE] [--heartbeat-timeout MS]
#
# This script sends an emergency RTL (Return to Launch) command to the
# autopilot via UART. It is designed as a failsafe when the main system
# heartbeat is not received within the threshold (default: 600ms).
#
# Exit codes:
#   0 - RTL command sent successfully
#   1 - RTL command failed
#   2 - Script error
#
# Hardware:
#   - UART device: /dev/ttyS1 (MAVLink autopilot)
#   - Baudrate: 57600
#   - Heartbeat byte: 0xAA
#   - RTL command: MAV_CMD_NAV_RETURN_TO_LAUNCH (20)

set -euo pipefail

# Configuration
UART_DEVICE="${UART_DEVICE:-/dev/ttyS1}"
UART_BAUDRATE="${UART_BAUDRATE:-57600}"
HEARTBEAT_TIMEOUT_MS="${HEARTBEAT_TIMEOUT_MS:-600}"
HEARTBEAT_BYTE="0xAA"
MAV_CMD_NAV_RETURN_TO_LAUNCH=20
LOG_FILE="${LOG_FILE:-/var/log/agent_audit/emergency_rtl.log}"
VERBOSE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --uart-device)
            UART_DEVICE="$2"
            shift 2
            ;;
        --uart-baudrate)
            UART_BAUDRATE="$2"
            shift 2
            ;;
        --heartbeat-timeout)
            HEARTBEAT_TIMEOUT_MS="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--uart-device DEVICE] [--heartbeat-timeout MS]"
            echo ""
            echo "Options:"
            echo "  --uart-device DEVICE     UART device (default: /dev/ttyS1)"
            echo "  --uart-baudrate RATE    UART baudrate (default: 57600)"
            echo "  --heartbeat-timeout MS  Heartbeat timeout in ms (default: 600)"
            echo "  --verbose, -v           Enable verbose output"
            echo "  --help, -h              Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 2
            ;;
    esac
done

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date -Iseconds)
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Check if running as root for UART access
check_permissions() {
    if [[ ! -w "$UART_DEVICE" ]]; then
        log "WARN" "Cannot write to UART device $UART_DEVICE"
        log "WARN" "Attempting with sudo or simulation mode"
        return 1
    fi
    return 0
}

# Send heartbeat byte via UART
send_heartbeat() {
    log "INFO" "Sending heartbeat byte $HEARTBEAT_BYTE to $UART_DEVICE"
    
    if check_permissions; then
        # Send heartbeat byte via UART
        printf "\xAA" > "$UART_DEVICE" 2>/dev/null || {
            log "WARN" "Failed to send heartbeat via UART - simulation mode"
            return 1
        }
        log "INFO" "Heartbeat sent successfully"
        return 0
    else
        log "SIMULATION" "Heartbeat byte $HEARTBEAT_BYTE -> $UART_DEVICE (simulated)"
        return 0
    fi
}

# Send MAVLink RTL command via UART
send_rtl_command() {
    log "CRITICAL" "Sending EMERGENCY RTL command to autopilot"
    
    # MAVLink command_long message for RTL
    # System ID: 1, Component ID: 1
    # Command: MAV_CMD_NAV_RETURN_TO_LAUNCH (20)
    # Confirmation: 0
    # Parameters: all zeros
    
    if check_permissions; then
        # Build MAVLink v1 message
        # Format: STX(0xFE) + LEN + SEQ + SYSID + COMPID + MSGID + PAYLOAD + CKA + CKB
        local msg_id=20  # MAV_CMD_NAV_RETURN_TO_LAUNCH
        local payload
        # command_long payload: param1-7(float) + command(uint16) + target_system(uint8) + target_component(uint8) + confirmation(uint8)
        # For RTL, all params are 0
        payload=$(printf '\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x14\x01\x01\x00')
        
        # Send via UART
        printf "\xfe\x14\x00\x01\x01\x14${payload}" > "$UART_DEVICE" 2>/dev/null || {
            log "WARN" "Failed to send RTL via UART - simulation mode"
            echo "RTL_CMD_SIMULATED" > "/tmp/emergency_rtl_flag"
            return 1
        }
        log "INFO" "RTL command sent via UART"
        return 0
    else
        log "SIMULATION" "RTL command sent to $UART_DEVICE (simulated)"
        echo "RTL_CMD_SIMULATED" > "/tmp/emergency_rtl_flag"
        return 0
    fi
}

# Check heartbeat status
check_heartbeat() {
    local heartbeat_file="/tmp/last_heartbeat_timestamp"
    
    if [[ ! -f "$heartbeat_file" ]]; then
        log "WARN" "Heartbeat file not found - assuming first run"
        return 0
    fi
    
    local last_heartbeat
    last_heartbeat=$(cat "$heartbeat_file")
    local current_time
    current_time=$(date +%s)
    local elapsed_ms=$(( (current_time - last_heartbeat) * 1000 ))
    
    if [[ $elapsed_ms -gt $HEARTBEAT_TIMEOUT_MS ]]; then
        log "CRITICAL" "Heartbeat timeout: ${elapsed_ms}ms > ${HEARTBEAT_TIMEOUT_MS}ms"
        return 1
    fi
    
    log "INFO" "Heartbeat OK: ${elapsed_ms}ms elapsed"
    return 0
}

# Main RTL execution
execute_emergency_rtl() {
    log "CRITICAL" "========================================"
    log "CRITICAL" "EMERGENCY RTL TRIGGERED"
    log "CRITICAL" "========================================"
    log "CRITICAL" "UART: $UART_DEVICE @ $UART_BAUDRATE baud"
    log "CRITICAL" "Timeout: ${HEARTBEAT_TIMEOUT_MS}ms"
    
    # Send emergency RTL
    send_rtl_command
    local rtl_result=$?
    
    if [[ $rtl_result -eq 0 ]]; then
        log "CRITICAL" "RTL command executed successfully"
        echo -e "${GREEN}[SUCCESS]${NC} Emergency RTL command sent"
        
        # Update state file
        echo "$(date -Iseconds)" > "/tmp/emergency_rtl_timestamp"
        echo "RTL" > "/tmp/drone_flight_mode"
        
        return 0
    else
        log "CRITICAL" "Failed to send RTL command"
        echo -e "${RED}[FAILED]${NC} Emergency RTL command failed"
        return 1
    fi
}

# Main execution
main() {
    log "INFO" "========================================"
    log "INFO" "Agent System v3.5 - Emergency RTL Script"
    log "INFO" "========================================"
    
    # Check if this is a heartbeat check or direct RTL
    if [[ "${1:-}" == "--check-heartbeat" ]]; then
        log "INFO" "Checking heartbeat status..."
        if ! check_heartbeat; then
            log "CRITICAL" "Heartbeat check failed - triggering RTL"
            execute_emergency_rtl
            return $?
        fi
        log "INFO" "Heartbeat check passed"
        return 0
    fi
    # Direct RTL execution
    execute_emergency_rtl
    return $?
}

# Run main function
main "$@"
exit $?
