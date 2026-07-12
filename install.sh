#!/usr/bin/env bash
#
# Chrome Agent Extension Installer
# Sets up Native Messaging Host and prepares extension for loading
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
NATIVE_HOST_NAME="com.browseruse.chrome_agent"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

detect_chrome_profile() {
    local profile_path=""

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        profile_path="$HOME/Library/Application Support/Google/Chrome"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        profile_path="$HOME/.config/google-chrome"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        # Windows
        profile_path="$LOCALAPPDATA/Google/Chrome/User Data"
    fi

    echo "$profile_path"
}

generate_native_host_manifest() {
    local extension_path="$1"
    local manifest_path="$2"

    # Find Python executable
    local python_path="${PROJECT_ROOT}/chrome_agent/native_host/launcher.sh"

    cat > "$manifest_path" <<EOF
{
  "name": "$NATIVE_HOST_NAME",
  "description": "Chrome Agent Native Messaging Host",
  "path": "$python_path",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://*"
  ]
}
EOF
}

main() {
    log_info "Chrome Agent Extension Installer"
    log_info "================================="

    # Detect Chrome profile
    local chrome_profile
    chrome_profile=$(detect_chrome_profile)

    if [[ -z "$chrome_profile" ]]; then
        log_error "Could not detect Chrome profile. Please specify manually."
        exit 1
    fi

    log_info "Chrome profile: $chrome_profile"

    # Create Native Messaging Host directory
    local native_host_dir="$chrome_profile/NativeMessagingHosts"
    mkdir -p "$native_host_dir"

    # Generate Native Host manifest
    local manifest_path="$native_host_dir/$NATIVE_HOST_NAME.json"
    generate_native_host_manifest "$PROJECT_ROOT/extension" "$manifest_path"

    log_info "Native Host manifest: $manifest_path"

    # Create launcher script
    local launcher_path="${PROJECT_ROOT}/chrome_agent/native_host/launcher.sh"
    mkdir -p "$(dirname "$launcher_path")"
    cat > "$launcher_path" <<EOF
#!/usr/bin/env bash
# Auto-generated launcher for Chrome Agent Native Host
exec "$(which python3)" "${PROJECT_ROOT}/chrome_agent/native_host/native_host.py"
EOF
    chmod +x "$launcher_path"

    log_info "Launcher: $launcher_path"

    # Verify extension structure
    log_info "Verifying extension structure..."
    local ext_dir="$PROJECT_ROOT/extension"

    for file in "manifest.json" "background.js" "content.js"; do
        if [[ ! -f "$ext_dir/$file" ]]; then
            log_error "Missing: $file"
            exit 1
        fi
        log_info "✓ $file"
    done

    for icon in "icon16.png" "icon48.png" "icon128.png"; do
        if [[ ! -f "$ext_dir/icons/$icon" ]]; then
            log_warn "Missing icon: $icon (using placeholder)"
        fi
    done

    log_info ""
    log_info "Installation complete!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Open Chrome and navigate to chrome://extensions"
    log_info "2. Enable Developer mode (top right)"
    log_info "3. Click Load unpacked and select: $ext_dir"
    log_info "4. Note the extension ID (e.g., abcdefgh...)"
    log_info "5. Update allowed_origins in $manifest_path with the real extension ID"
    log_info ""
    log_info "To test: chrome-agent ensure --launch-if-missing"
}

main "$@"
