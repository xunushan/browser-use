#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_NAME="com.browseruse.chrome_agent"
EXTENSION_ID="${1:-${CHROME_AGENT_EXTENSION_ID:-}}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "V1 installer currently supports macOS only." >&2
  exit 2
fi

if [[ ! "$EXTENSION_ID" =~ ^[a-p]{32}$ ]]; then
  echo "Usage: ./install.sh <Chrome extension ID>" >&2
  echo "First load ${PROJECT_DIR}/extension in chrome://extensions, then copy its ID." >&2
  exit 2
fi

BOOTSTRAP_PYTHON="${PYTHON_BIN:-$(command -v python3)}"
VENV_DIR="${CHROME_AGENT_VENV:-$HOME/.local/share/chrome-agent/venv}"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install -e "$PROJECT_DIR"
PYTHON_BIN="$VENV_DIR/bin/python"

LAUNCHER_PATH="$PROJECT_DIR/chrome_agent/native_host/launcher.sh"
HOST_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
HOST_MANIFEST="$HOST_DIR/$HOST_NAME.json"
SKILL_SOURCE="$PROJECT_DIR/.claude/skills/chrome-agent"
SKILL_DIRS=("$HOME/.claude/skills" "${CODEX_HOME:-$HOME/.codex}/skills")
BIN_DIR="$HOME/.local/bin"
CLI_TARGET="$BIN_DIR/chrome-agent"

mkdir -p "$HOST_DIR" "$BIN_DIR" "${SKILL_DIRS[@]}"

python3 - "$LAUNCHER_PATH" "$PYTHON_BIN" "$PROJECT_DIR" <<'PY'
import os
import sys
from pathlib import Path

path, python_bin, project_dir = map(Path, sys.argv[1:])
path.write_text(
    "#!/usr/bin/env bash\n"
    f'exec "{python_bin}" "{project_dir}/chrome_agent/native_host/native_host.py"\n',
    encoding="utf-8",
)
os.chmod(path, 0o755)
PY

python3 - "$HOST_MANIFEST" "$HOST_NAME" "$LAUNCHER_PATH" "$EXTENSION_ID" <<'PY'
import json
import sys
from pathlib import Path

path, name, launcher, extension_id = sys.argv[1:]
manifest = {
    "name": name,
    "description": "Chrome Agent Native Messaging Host",
    "path": launcher,
    "type": "stdio",
    "allowed_origins": [f"chrome-extension://{extension_id}/"],
}
Path(path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

for SKILL_DIR in "${SKILL_DIRS[@]}"; do
  SKILL_TARGET="$SKILL_DIR/chrome-agent"
  if [[ -L "$SKILL_TARGET" ]]; then
    current_target="$(readlink "$SKILL_TARGET")"
    if [[ "$current_target" != "$SKILL_SOURCE" ]]; then
      echo "Refusing to replace existing skill symlink: $SKILL_TARGET -> $current_target" >&2
      exit 3
    fi
  elif [[ -e "$SKILL_TARGET" ]]; then
    echo "Refusing to replace existing skill: $SKILL_TARGET" >&2
    exit 3
  else
    ln -s "$SKILL_SOURCE" "$SKILL_TARGET"
  fi
done

if [[ -e "$CLI_TARGET" && ! -L "$CLI_TARGET" ]]; then
  echo "Refusing to replace existing CLI: $CLI_TARGET" >&2
  exit 3
fi
ln -sfn "$VENV_DIR/bin/chrome-agent" "$CLI_TARGET"

echo "Installed CLI, daemon, Native Messaging Host, and Chrome Agent Skill."
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "Add $BIN_DIR to PATH before invoking chrome-agent by name."
fi
echo "Reload Chrome Agent in chrome://extensions, then run:"
echo "  chrome-agent ensure --launch-if-missing --wait-for-extension --json"
