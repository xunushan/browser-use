#!/usr/bin/env bash
#
# Xiaohongshu E2E Test Script
# Tests the complete workflow: ensure -> tabs -> page operations
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Run CLI command and extract result
run_cli() {
    local cmd="$1"
    $VENV_PYTHON -m chrome_agent.cli $cmd --json 2>/dev/null
}

main() {
    log_info "Xiaohongshu E2E Test"
    log_info "======================"

    # Step 1: Ensure system is ready
    log_info "Step 1: Ensuring system is ready..."
    result=$(run_cli "ensure --launch-if-missing --wait-for-extension")
    if [[ $(echo "$result" | grep -o '"status": "ready"') ]]; then
        log_info "✓ System ready"
    else
        log_error "✗ System not ready: $result"
        exit 1
    fi

    # Step 2: List tabs
    log_info "Step 2: Listing tabs..."
    result=$(run_cli "tabs list")
    log_info "Tabs response: $result"

    # Step 3: Open Xiaohongshu
    log_info "Step 3: Opening xiaohongshu.com..."
    result=$(run_cli "tabs open https://www.xiaohongshu.com")
    log_info "Open response: $result"

    # Step 4: Wait for page to load
    log_info "Step 4: Waiting for page to load..."
    sleep 3

    # Step 5: List tabs again to find Xiaohongshu tab
    log_info "Step 5: Finding Xiaohongshu tab..."
    result=$(run_cli "tabs list --domain xiaohongshu.com")
    log_info "Tabs with domain: $result"

    # Step 6: Take snapshot
    log_info "Step 6: Taking page snapshot..."
    # Note: This requires a real tab ID
    # result=$(run_cli "page snapshot --tab-id 0")
    # log_info "Snapshot: $result"

    log_info ""
    log_info "E2E test completed!"
    log_info "Note: Full page operations require a real tab ID from Chrome."
}

main "$@"
