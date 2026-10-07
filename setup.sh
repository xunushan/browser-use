#!/usr/bin/env bash
# Set up Chrome Agent on this machine: the runtime, the Native Messaging host,
# and the skill link that makes this directory an agent skill.
#
# Run from the checkout, which is also the skill: `chrome_agent/` and
# `extension/` sit next to this script, so once the directory is linked into an
# agent's skill directory, the agent that reads SKILL.md can run this itself.
#
# The extension is not installed here: Chrome has no silent install, so the user
# loads extension/ at chrome://extensions by hand. This script prints which
# folder to pick and stops there.
set -euo pipefail

HOST_NAME="com.browseruse.chrome_agent"
SKILL_NAME="chrome-agent"

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RUNTIME_DIR="${CHROME_AGENT_HOME:-$HOME/.chrome-agent}"
VENV_DIR="${CHROME_AGENT_VENV:-$RUNTIME_DIR/venv}"
BIN_DIR="${CHROME_AGENT_BIN_DIR:-$HOME/.local/bin}"
HOST_DIR="${CHROME_AGENT_HOST_DIR:-$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts}"
SKILL_DIRS_DEFAULT="$HOME/.claude/skills $HOME/.codex/skills"

EXTENSION_ID_OVERRIDE=""
SKILL_DIRS_OVERRIDE=""
UNINSTALL=0
PURGE=0
FORCE=0

usage() {
  cat <<'TEXT'
Usage: ./setup.sh [options]

  --extension-id <id>    use this 32-character ID for the Native Messaging host
                         instead of the one the manifest key pins
  --skill-dirs "<dirs>"  space-separated skill directories, default
                         "~/.claude/skills ~/.codex/skills"
  --force                replace skill directories this script did not create
  --uninstall            remove the host manifest, launcher, skill links and CLI
  --purge                with --uninstall, also delete the virtualenv
  -h, --help             this text
TEXT
}

die() {
  echo "$*" >&2
  exit 2
}

while (($#)); do
  case "$1" in
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
  die "Only macOS is supported so far."
fi

read -r -a SKILL_DIRS <<<"${SKILL_DIRS_OVERRIDE:-$SKILL_DIRS_DEFAULT}"

if ((UNINSTALL)); then
  rm -f "$HOST_DIR/$HOST_NAME.json" "$RUNTIME_DIR/launcher.sh" "$RUNTIME_DIR/install.json"
  if [[ -L "$BIN_DIR/chrome-agent" ]]; then
    rm -f "$BIN_DIR/chrome-agent"
  fi
  for SKILL_DIR in "${SKILL_DIRS[@]}"; do
    TARGET="$SKILL_DIR/$SKILL_NAME"
    # Only links are ours to remove: a real directory here was put there by
    # someone who did not use this script.
    if [[ -L "$TARGET" ]]; then
      rm -f "$TARGET"
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

if [[ ! -f "$SOURCE_DIR/pyproject.toml" || ! -f "$SOURCE_DIR/SKILL.md" ]]; then
  die "$SOURCE_DIR is not the chrome-agent skill; run this from the checkout."
fi

UV="${UV_BIN:-$(command -v uv || true)}"
if [[ -z "$UV" ]]; then
  die "uv is required, and it also keeps pip out of the picture:
  curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$UV" venv "$VENV_DIR" --quiet
fi
VENV_PYTHON="$VENV_DIR/bin/python"

# Editable: the skill is the checkout, so an edit in the tree must take effect
# without reinstalling. --reinstall because the wheel is built from this tree.
"$UV" pip install --quiet --python "$VENV_PYTHON" --reinstall -e "$SOURCE_DIR"

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
# Written by setup.sh. Chrome runs this to reach the daemon; the interpreter is
# named absolutely because Chrome does not inherit a shell environment.
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

for SKILL_DIR in "${SKILL_DIRS[@]}"; do
  mkdir -p "$SKILL_DIR"
  TARGET="$SKILL_DIR/$SKILL_NAME"
  # Already this skill, in this very place: nothing to link. That is the normal
  # case when the skill was installed by unpacking it into the skill directory
  # and this script is then run from inside that installation. It must not fall
  # through to the replacement below, which would delete the running copy and
  # leave a symlink pointing at itself.
  #
  # -ef compares the files themselves, so it holds however the paths are spelt.
  if [[ -e "$TARGET" && "$TARGET" -ef "$SOURCE_DIR" ]]; then
    echo "skill already in place at $TARGET"
    continue
  fi
  if [[ -L "$TARGET" ]]; then
    rm -f "$TARGET"
  elif [[ -e "$TARGET" ]]; then
    if grep -q "^name: $SKILL_NAME$" "$TARGET/SKILL.md" 2>/dev/null || ((FORCE)); then
      rm -rf "$TARGET"
    else
      die "Refusing to replace $TARGET: it is not a $SKILL_NAME skill. Use --force."
    fi
  fi
  ln -s "$SOURCE_DIR" "$TARGET"
done

VERSION="$("$VENV_PYTHON" -c 'import chrome_agent; print(chrome_agent.__version__)')"

"$VENV_PYTHON" - "$RUNTIME_DIR/install.json" "$VERSION" "$EXTENSION_ID" \
  "${SKILL_DIRS[0]}/$SKILL_NAME" "$EXTENSION_DIR" "$SOURCE_DIR" <<'PY'
import datetime
import json
import sys
from pathlib import Path

path, version, extension_id, skill_dir, extension_dir, source_dir = sys.argv[1:]
Path(path).write_text(
    json.dumps(
        {
            "version": version,
            "extensionId": extension_id,
            "skillDir": skill_dir,
            "extensionDir": extension_dir,
            "sourceDir": source_dir,
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

# ---------------------------------------------------------------- the manual

echo "Configured Chrome Agent $VERSION."
echo "  extension ID  $EXTENSION_ID"
echo "  launcher      $LAUNCHER"
echo "  host manifest $HOST_DIR/$HOST_NAME.json"
echo "  skill         ${SKILL_DIRS[*]}"
echo
echo "One step left, and it needs the user:"
echo "  1. chrome://extensions -> Developer mode -> Load unpacked -> $EXTENSION_DIR"
echo "     The card must then read the ID above; if it does not, the folder picked"
echo "     was not this one."
echo "  2. chrome-agent ensure --launch-if-missing --wait-for-extension --json"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo
  echo "note: $BIN_DIR is not on PATH; invoke $BIN_DIR/chrome-agent or add it."
fi
