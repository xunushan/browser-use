#!/usr/bin/env bash
#
# Secure API Key configuration script
# Reads API key from file and stores it securely
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Find API key file
find_api_key_file() {
    # Check common locations
    local locations=(
        "$PROJECT_ROOT/.env"
        "$PROJECT_ROOT/api.key"
        "$PROJECT_ROOT/.api_key"
        "$HOME/.chrome-agent/api.key"
    )

    for location in "${locations[@]}"; do
        if [[ -f "$location" ]]; then
            echo "$location"
            return 0
        fi
    done

    return 1
}

# Read API key from file (securely)
read_api_key() {
    local file="$1"
    # Read first line, trim whitespace
    head -n 1 "$file" | tr -d '[:space:]'
}

# Store API key using Python config manager
store_api_key() {
    local api_key="$1"

    python3 <<EOF
import sys
sys.path.insert(0, "${PROJECT_ROOT}")
from chrome_agent.utils.config import ConfigManager

config = ConfigManager()
try:
    config.set_api_key("glm", "${api_key}")
    print("API key stored successfully")
except Exception as e:
    print(f"Error storing API key: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

main() {
    log_info "Chrome Agent API Key Configuration"
    log_info "==================================="

    # Find API key file
    local api_key_file
    if ! api_key_file=$(find_api_key_file); then
        log_error "No API key file found"
        log_info "Please create one of the following files with your API key:"
        log_info "  - ${PROJECT_ROOT}/.env"
        log_info "  - ${PROJECT_ROOT}/api.key"
        log_info "  - ~/.chrome-agent/api.key"
        exit 1
    fi

    log_info "Found API key file: $api_key_file"

    # Read API key
    local api_key
    api_key=$(read_api_key "$api_key_file")

    if [[ -z "$api_key" ]]; then
        log_error "API key file is empty"
        exit 1
    fi

    # Validate API key format (basic check)
    if [[ ${#api_key} -lt 10 ]]; then
        log_error "API key appears too short"
        exit 1
    fi

    log_info "API key loaded (length: ${#api_key} chars)"

    # Store securely
    store_api_key "$api_key"

    # Clean up source file (optional, for security)
    log_info "Remove source file? (y/N)"
    read -r response
    if [[ "$response" == "y" || "$response" == "Y" ]]; then
        rm "$api_key_file"
        log_info "Source file removed"
    fi

    log_info ""
    log_info "Configuration complete!"
    log_info "API key is now stored securely and will be used by Chrome Agent."
}

main "$@"
