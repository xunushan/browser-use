#!/usr/bin/env bash
# Install Chrome Agent: the runtime, the Native Messaging host, and the skill.
#
# Two modes, told apart by what sits next to this script:
#   checkout  pyproject.toml is here. Build a wheel from the tree, install it
#             into the venv, and link the skill back into the tree so edits take
#             effect without reinstalling.
#   bundle    a chrome_agent-*.whl is here. Install it as-is and copy the skill,
#             so the unpacked release directory is the only thing needed and the
#             repository can be deleted afterwards.
#
# The extension is not installed here: it is loaded by hand at
# chrome://extensions, from extension/ in a checkout or from the bundle.
set -euo pipefail

HOST_NAME="com.browseruse.chrome_agent"
SKILL_NAME="chrome-agent"

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${CHROME_AGENT_HOME:-$HOME/.chrome-agent}"
VENV_DIR="${CHROME_AGENT_VENV:-$RUNTIME_DIR/venv}"
BIN_DIR="${CHROME_AGENT_BIN_DIR:-$HOME/.local/bin}"
HOST_DIR="${CHROME_AGENT_HOST_DIR:-$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts}"
SKILL_DIRS_DEFAULT="$HOME/.claude/skills $HOME/.codex/skills"

MODE=""
FROM_DIR=""
EXTENSION_ID_OVERRIDE=""
SKILL_DIRS_OVERRIDE=""
UNINSTALL=0
PURGE=0
FORCE=0

usage() {
  cat <<'TEXT'
Usage: ./install.sh [options]

  --from <dir>         install from a release directory (wheel + extension/ +
                       skill/), instead of from this checkout
  --extension-id <id>  use this 32-character ID for the Native Messaging host
                       instead of the one the manifest key pins
  --skill-dirs "<dirs>"  space-separated skill directories, default
                       "~/.claude/skills ~/.codex/skills"
  --uninstall          remove the host manifest, launcher, skill links and CLI
  --purge              with --uninstall, also delete the virtualenv
  --force              replace skill directories this script did not create
  -h, --help           this text
TEXT
}

die() {
  echo "$*" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --from) FROM_DIR="${2:?--from needs a directory}"; shift 2 ;;
    --extension-id) EXTENSION_ID_OVERRIDE="${2:?--extension-id needs an ID}"; shift 2 ;;
    --skill-dirs) SKILL_DIRS_OVERRIDE="${2:?--skill-dirs needs a list}"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge) PURGE=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  die "The V1 installer currently supports macOS only."
fi

read -r -a SKILL_DIRS <<<"${SKILL_DIRS_OVERRIDE:-$SKILL_DIRS_DEFAULT}"

if [[ -n "$FROM_DIR" ]]; then
  SOURCE_DIR="$(cd "$FROM_DIR" && pwd)"
fi

if ((UNINSTALL)); then
  rm -f "$HOST_DIR/$HOST_NAME.json" "$RUNTIME_DIR/launcher.sh" "$RUNTIME_DIR/install.json"
  if [[ -L "$BIN_DIR/chrome-agent" ]]; then
    rm -f "$BIN_DIR/chrome-agent"
  fi
  for SKILL_DIR in "${SKILL_DIRS[@]}"; do
    TARGET="$SKILL_DIR/$SKILL_NAME"
    if [[ -L "$TARGET" || -d "$TARGET" ]]; then
      rm -rf "$TARGET"
    fi
  done
  if ((PURGE)); then
    rm -rf "$VENV_DIR"
  fi
  echo "Removed the Native Messaging host, launcher, skill links and CLI."
  echo "The extension itself is removed at chrome://extensions."
  exit 0
fi

# ---------------------------------------------------------------- the runtime

if [[ -f "$SOURCE_DIR/pyproject.toml" ]]; then
  MODE="checkout"
elif compgen -G "$SOURCE_DIR/chrome_agent-*.whl" >/dev/null; then
  MODE="bundle"
else
  die "$SOURCE_DIR holds neither pyproject.toml nor chrome_agent-*.whl"
fi

BOOTSTRAP_PYTHON="${PYTHON_BIN:-$(command -v python3 || true)}"
if [[ -z "$BOOTSTRAP_PYTHON" ]]; then
  die "python3 is required."
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ "$MODE" == "checkout" ]]; then
  WHEEL_DIR="$RUNTIME_DIR/build"
  mkdir -p "$WHEEL_DIR"
  rm -f "$WHEEL_DIR"/chrome_agent-*.whl
  "$VENV_PYTHON" -m pip wheel --quiet --no-deps --wheel-dir "$WHEEL_DIR" "$SOURCE_DIR"
  WHEEL="$(ls -t "$WHEEL_DIR"/chrome_agent-*.whl | head -1)"
else
  WHEEL="$(ls -t "$SOURCE_DIR"/chrome_agent-*.whl | head -1)"
fi

# The wheel carries chrome_agent/ only, so its dependencies are resolved here
# rather than dragged along: repeating an install must not require the network
# for packages that are already in the venv.
"$VENV_PYTHON" -m pip install --quiet --force-reinstall --no-deps "$WHEEL"
"$VENV_PYTHON" -m pip install --quiet click PyYAML

# ------------------------------------------------------------- the extension

EXTENSION_DIR="$SOURCE_DIR/extension"
EXTENSION_ID="$EXTENSION_ID_OVERRIDE"
if [[ -z "$EXTENSION_ID" ]]; then
  EXTENSION_ID="$("$VENV_PYTHON" - "$EXTENSION_DIR/manifest.json" <<'PY'
import sys
from pathlib import Path

from chrome_agent.utils.extension_id import manifest_extension_id

print(manifest_extension_id(Path(sys.argv[1])) or "")
PY
)"
fi

if [[ ! "$EXTENSION_ID" =~ ^[a-p]{32}$ ]]; then
  die "No usable extension ID. $EXTENSION_DIR/manifest.json should carry a 'key'
that pins one; load the extension at chrome://extensions and pass the ID it
shows with --extension-id <id> if you deliberately loaded it without the key."
fi

# --------------------------------------------------- the Native Messaging host

mkdir -p "$RUNTIME_DIR" "$HOST_DIR"

LAUNCHER="$RUNTIME_DIR/launcher.sh"
cat >"$LAUNCHER" <<TEXT
#!/bin/sh
# Written by install.sh. Chrome runs this to reach the daemon; it lives outside
# the source tree on purpose, so the checkout may be moved or deleted.
exec "$VENV_PYTHON" -m chrome_agent.native_host.native_host
TEXT
chmod 755 "$LAUNCHER"

"$VENV_PYTHON" - "$HOST_DIR/$HOST_NAME.json" "$HOST_NAME" "$LAUNCHER" "$EXTENSION_ID" <<'PY'
import json
import sys
from pathlib import Path

path, name, launcher, extension_id = sys.argv[1:]
Path(path).write_text(
    json.dumps(
        {
            "name": name,
            "description": "Chrome Agent Native Messaging Host",
            "path": launcher,
            "type": "stdio",
            "allowed_origins": [f"chrome-extension://{extension_id}/"],
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

# ----------------------------------------------------------------- the skill

SKILL_SOURCE="$SOURCE_DIR/skill/$SKILL_NAME"
if [[ ! -f "$SKILL_SOURCE/SKILL.md" ]]; then
  die "$SKILL_SOURCE/SKILL.md is missing."
fi

for SKILL_DIR in "${SKILL_DIRS[@]}"; do
  mkdir -p "$SKILL_DIR"
  TARGET="$SKILL_DIR/$SKILL_NAME"
  if [[ -L "$TARGET" ]]; then
    # A symlink here is either ours or a stale one of ours pointing at a path
    # that no longer exists; both are safe to replace.
    rm -f "$TARGET"
  elif [[ -e "$TARGET" ]]; then
    if grep -q "^name: $SKILL_NAME$" "$TARGET/SKILL.md" 2>/dev/null || ((FORCE)); then
      rm -rf "$TARGET"
    else
      die "Refusing to replace $TARGET: it is not a $SKILL_NAME skill. Use --force."
    fi
  fi
  if [[ "$MODE" == "checkout" ]]; then
    ln -s "$SKILL_SOURCE" "$TARGET"
  else
    cp -R "$SKILL_SOURCE" "$TARGET"
    find "$TARGET" -name '__pycache__' -type d -prune -exec rm -rf {} +
  fi
done

VERSION="$("$VENV_PYTHON" -c 'import chrome_agent; print(chrome_agent.__version__)')"

"$VENV_PYTHON" - "$RUNTIME_DIR/install.json" "$VERSION" "$EXTENSION_ID" \
  "${SKILL_DIRS[0]}/$SKILL_NAME" "$EXTENSION_DIR" "$SOURCE_DIR" "$MODE" <<'PY'
import datetime
import json
import sys
from pathlib import Path

path, version, extension_id, skill_dir, extension_dir, source_dir, mode = sys.argv[1:]
Path(path).write_text(
    json.dumps(
        {
            "version": version,
            "extensionId": extension_id,
            "skillDir": skill_dir,
            "extensionDir": extension_dir,
            "sourceDir": source_dir,
            "mode": mode,
            "installedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

# ------------------------------------------------------------------- the CLI

mkdir -p "$BIN_DIR"
if [[ -e "$BIN_DIR/chrome-agent" && ! -L "$BIN_DIR/chrome-agent" ]]; then
  die "Refusing to replace $BIN_DIR/chrome-agent: it is not a symlink."
fi
ln -sfn "$VENV_DIR/bin/chrome-agent" "$BIN_DIR/chrome-agent"

# --------------------------------------------------------------------- done

echo "Installed Chrome Agent $VERSION ($MODE)."
echo "  extension ID  $EXTENSION_ID"
echo "  launcher      $LAUNCHER"
echo "  host manifest $HOST_DIR/$HOST_NAME.json"
echo "  skill         ${SKILL_DIRS[*]}"
echo
echo "Next:"
echo "  1. chrome://extensions -> reload the extension; its ID must read $EXTENSION_ID"
echo "  2. chrome-agent ensure --launch-if-missing --wait-for-extension --json"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "  note: add $BIN_DIR to PATH before invoking chrome-agent by name"
fi
