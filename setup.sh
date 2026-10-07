#!/usr/bin/env bash
# Set up Chrome Agent on this machine: the runtime, the Native Messaging host,
# the copy of the extension Chrome loads, and the manual in the agent's skill
# directory.
#
# Run from the checkout. The runtime is installed out of it into an install home
# of its own, and the manual is copied into the skill directory — the skill
# directory holds the manual and nothing else, so an agent reading it finds a
# description of the tool rather than the tool.
#
# Chrome has no silent way to load an extension, so the user loads it once by
# hand at chrome://extensions. Everything after that is this script's job: it
# copies the extension out of the checkout to a fixed path an update cannot
# move, and when that copy has changed since the extension last loaded
# it, it has the extension reload itself. Re-running this script therefore asks
# nothing of the user, and it looks before it tells: a machine that is already
# set up is left alone.
set -euo pipefail

HOST_NAME="com.browseruse.chrome_agent"
SKILL_NAME="chrome-agent"

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# Not a dot directory, deliberately: the folder below is the one a person has to
# pick in Chrome's "Load unpacked" dialog, and macOS file dialogs do not list dot
# directories — ~/.chrome-agent/extension cannot be selected there at all.
RUNTIME_DIR="${CHROME_AGENT_HOME:-$HOME/chrome-agent}"
VENV_DIR="${CHROME_AGENT_VENV:-$RUNTIME_DIR/venv}"
BIN_DIR="${CHROME_AGENT_BIN_DIR:-$HOME/.local/bin}"
SKILL_DIRS_DEFAULT="$HOME/.claude/skills"

# Chrome loads the extension from a fixed path rather than from the checkout:
# the checkout is a build input, and Chrome remembers the path it loaded from,
# so an extension loaded out of it would stop working the moment that directory
# moved or was deleted. The copy below is the one Chrome points at; this script
# keeps it in step with the source.
EXTENSION_SOURCE="$SOURCE_DIR/extension"
EXTENSION_DIR="$RUNTIME_DIR/extension"

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
                         "~/.claude/skills"
  --force                replace skill directories this script did not create
  --uninstall            remove the host manifest, launcher, skill links and CLI
  --purge                with --uninstall, also delete the virtualenv and the
                         copy of the extension Chrome loads
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

# Chrome reads the host manifest from a per-user directory that differs by
# platform and by browser. Chrome's own is the default, and CHROME_AGENT_HOST_DIR
# overrides it; Chromium keeps its own, ~/.config/chromium/NativeMessagingHosts
# on Linux and ~/Library/Application Support/Chromium/NativeMessagingHosts on
# macOS. The paths come from the Native Messaging documentation, which places
# user-level manifests in a NativeMessagingHosts/ directory inside the user data
# directory (developer.chrome.com/docs/extensions/develop/concepts/native-messaging),
# and they are the ones Chromium's own install_host.sh example uses.
case "$(uname -s)" in
  Darwin)
    HOST_DIR_DEFAULT="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
    ;;
  Linux)
    HOST_DIR_DEFAULT="$HOME/.config/google-chrome/NativeMessagingHosts"
    ;;
  *)
    die "Unsupported platform: $(uname -s). Windows registers the host in the
registry rather than in a directory, and this script does not do that yet."
    ;;
esac
HOST_DIR="${CHROME_AGENT_HOST_DIR:-$HOST_DIR_DEFAULT}"

read -r -a SKILL_DIRS <<<"${SKILL_DIRS_OVERRIDE:-$SKILL_DIRS_DEFAULT}"

# Installations from before the home left ~/.chrome-agent are reported, not
# moved. Nothing in there is state this script needs — the venv is rebuilt below
# — and it is not only this script's property: it can hold a key and a secret
# that belong to whoever put them there. The report is at the end, with the
# other things this run has to say.
LEGACY_RUNTIME_DIR="$HOME/.chrome-agent"

if ((UNINSTALL)); then
  rm -f "$HOST_DIR/$HOST_NAME.json" "$RUNTIME_DIR/launcher.sh" "$RUNTIME_DIR/install.json"
  if [[ -L "$BIN_DIR/chrome-agent" ]]; then
    rm -f "$BIN_DIR/chrome-agent"
  fi
  for SKILL_DIR in "${SKILL_DIRS[@]}"; do
    TARGET="$SKILL_DIR/$SKILL_NAME"
    # The manual this script wrote is this script's to remove. Anything else at
    # that path belongs to whoever put it there, and the helper says so rather
    # than deleting it — a skill directory is small enough that removing the
    # wrong one looks like a success.
    if [[ -x "$VENV_DIR/bin/python" ]]; then
      "$VENV_DIR/bin/python" - "$TARGET" <<'PY' || true
import sys
from pathlib import Path

from chrome_agent.utils.skill_sync import remove_skill

try:
    removed = remove_skill(Path(sys.argv[1]))
except FileExistsError as error:
    print(f"  left alone: {error}", file=sys.stderr)
else:
    if removed:
        print(f"  removed {sys.argv[1]}")
PY
    elif [[ -L "$TARGET" ]]; then
      # No runtime to ask, so only the case that needs no judgement.
      rm -f "$TARGET"
    fi
  done
  if ((PURGE)); then
    rm -rf "$VENV_DIR"
    # The copy Chrome loads is left in place otherwise: a loaded extension
    # points at it, and deleting it would leave the extension broken rather
    # than gone.
    rm -rf "$EXTENSION_DIR"
  fi
  echo "Removed the Native Messaging host, launcher, skill links and CLI."
  echo "The extension itself is removed at chrome://extensions."
  if ((!PURGE)); then
    echo "Its files are still at $EXTENSION_DIR; delete that folder too once the"
    echo "extension is gone, or rerun with --purge."
  fi
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

# A real install, not editable. The runtime belongs in the install home, where
# nothing about the checkout can move it: `chrome-agent` is the tool, and the
# skill directory describes the tool rather than being it. The price is that an
# edit in the tree reaches this machine only when this script runs again — which
# is also the run that copies the manual out, so the two stay in step.
# --reinstall because the wheel is built from this tree.
"$UV" pip install --quiet --python "$VENV_PYTHON" --reinstall "$SOURCE_DIR"

# ------------------------------------------------------------- the extension

EXTENSION_ID="$EXTENSION_ID_OVERRIDE"
if [[ -z "$EXTENSION_ID" ]]; then
  EXTENSION_ID="$("$VENV_PYTHON" - "$EXTENSION_SOURCE/manifest.json" <<'PY'
import sys
from pathlib import Path

from chrome_agent.utils.extension_id import manifest_extension_id

print(manifest_extension_id(Path(sys.argv[1])) or "")
PY
)"
fi

if [[ ! "$EXTENSION_ID" =~ ^[a-p]{32}$ ]]; then
  die "No usable extension ID. $EXTENSION_SOURCE/manifest.json should carry a 'key'
that pins one; load the extension at chrome://extensions and pass the ID it
shows with --extension-id <id> if you deliberately loaded it without the key."
fi

CURRENT_HASH="$("$VENV_PYTHON" - "$EXTENSION_SOURCE" "$EXTENSION_DIR" <<'PY'
import sys
from pathlib import Path

from chrome_agent.utils.extension_sync import sync_extension

print(sync_extension(Path(sys.argv[1]), Path(sys.argv[2])))
PY
)"

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

# The skill directory is the manual — SKILL.md and the references — and nothing
# else. It is copied rather than linked, so that an agent opening it finds a
# description of the tool instead of a second copy of the project. The copy is
# also what makes the checkout's location stop mattering; the price is that an
# edit here reaches the agent only when this script runs again.
#
# sync_skill refuses to replace a directory that is not this skill, and does
# nothing at all when the checkout is itself the skill directory — that case
# would delete the runtime to make room for four files.

SKILL_REPORT="$("$VENV_PYTHON" - "$SOURCE_DIR" "$FORCE" "${SKILL_DIRS[@]}" <<'PY'
import sys
from pathlib import Path

from chrome_agent.utils.skill_sync import SKILL_NAME, sync_skill

source, force, *dirs = sys.argv[1:]
force = force == "1"

for directory in dirs:
    target = Path(directory) / SKILL_NAME
    try:
        written = sync_skill(source, target, force=force)
    except FileExistsError as error:
        sys.exit(f"setup.sh: {error}")
    if written:
        print(f"  manual        {target}")
    else:
        print(f"  manual        {target} (left alone: the checkout is already here)")
PY
)"

VERSION="$("$VENV_PYTHON" -c 'import chrome_agent; print(chrome_agent.__version__)')"

"$VENV_PYTHON" - "$RUNTIME_DIR/install.json" "$VERSION" "$EXTENSION_ID" \
  "${SKILL_DIRS[0]}/$SKILL_NAME" "$EXTENSION_DIR" "$SOURCE_DIR" <<'PY'
import datetime
import json
import sys
from pathlib import Path

path, version, extension_id, skill_dir, extension_dir, source_dir = sys.argv[1:]
record = {
    "version": version,
    "extensionId": extension_id,
    "skillDir": skill_dir,
    "extensionDir": extension_dir,
    "sourceDir": source_dir,
    "installedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
# The hash of what the extension last confirmed it was running is not this
# script's to set: `extension reload` writes it once the extension is back.
# Carrying the old one over is what keeps a re-run from looking like a changed
# copy, and so from reloading an extension that never went anywhere.
try:
    previous = json.loads(Path(path).read_text(encoding="utf-8")).get("extensionHash")
except (OSError, ValueError):
    previous = None
if isinstance(previous, str):
    record["extensionHash"] = previous

Path(path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
PY

# ------------------------------------------------------------------- the CLI

mkdir -p "$BIN_DIR"
if [[ -e "$BIN_DIR/chrome-agent" && ! -L "$BIN_DIR/chrome-agent" ]]; then
  die "Refusing to replace $BIN_DIR/chrome-agent: it is not a symlink."
fi
ln -sfn "$VENV_DIR/bin/chrome-agent" "$BIN_DIR/chrome-agent"

# ------------------------------------------------------------- the extension

# Whether the extension is loaded is a question only the daemon can answer, so
# the daemon is started here: it is part of this installation either way. Chrome
# is not started — a browser opened by an installer is a browser nobody asked
# for, and an extension loaded once stays loaded without one.
"$BIN_DIR/chrome-agent" start >/dev/null 2>&1 || true

status_field() {
  "$VENV_PYTHON" -c '
import json, sys
try:
    status = json.loads(sys.argv[1])
except ValueError:
    status = {}
value = status.get(sys.argv[2])
print("" if value is None else value)
' "$1" "$2" 2>/dev/null || true
}

STATUS="$("$BIN_DIR/chrome-agent" extension status --json 2>/dev/null || true)"
CHROME_RUNNING="$(status_field "$STATUS" chromeRunning)"
CONNECTED="$(status_field "$STATUS" connected)"
LOADED_HASH="$(status_field "$STATUS" loadedHash)"

# A machine where the extension was loaded before is worth waiting on: it
# reconnects by itself, at worst one keep-alive apart, and waiting is what keeps
# this script from telling such a user to load what they already have.
if [[ "$CHROME_RUNNING" == "True" && "$CONNECTED" != "True" && -n "$LOADED_HASH" ]]; then
  for _ in $(seq 20); do
    sleep 1
    STATUS="$("$BIN_DIR/chrome-agent" extension status --json 2>/dev/null || true)"
    CONNECTED="$(status_field "$STATUS" connected)"
    if [[ "$CONNECTED" == "True" ]]; then break; fi
  done
fi

RELOAD_NEEDED="$(status_field "$STATUS" reloadNeeded)"

echo "Configured Chrome Agent $VERSION."
echo "  extension ID  $EXTENSION_ID"
echo "  extension     $EXTENSION_DIR"
echo "  launcher      $LAUNCHER"
echo "  host manifest $HOST_DIR/$HOST_NAME.json"
echo "  skill dirs    ${SKILL_DIRS[*]}"
printf '%s\n' "$SKILL_REPORT"
echo

if [[ "$CHROME_RUNNING" != "True" ]]; then
  echo "Chrome is not running, so the extension cannot be asked anything from here."
  echo "That is not a problem: this script does not start Chrome, and an extension"
  echo "that was loaded once stays loaded. Check again later with"
  echo "  chrome-agent extension status"
elif [[ "$CONNECTED" == "True" && "$RELOAD_NEEDED" == "True" ]]; then
  if "$BIN_DIR/chrome-agent" extension reload; then
    echo "The extension is now running the copy this script wrote."
  else
    echo "The extension did not come back after reloading; check chrome://extensions."
  fi
elif [[ "$CONNECTED" == "True" ]]; then
  echo "The extension is loaded and connected, and already on this copy. Nothing to do."
elif [[ -n "$LOADED_HASH" ]]; then
  echo "No extension is connected at the moment, but it was loaded here before, so"
  echo "there is nothing to load: Chrome has not woken it yet, and it reconnects on"
  echo "its own. If you did remove it from chrome://extensions, load it again:"
  echo "  chrome://extensions -> Developer mode -> Load unpacked -> $EXTENSION_DIR"
  echo "  The card must read $EXTENSION_ID; if it does not, that was not this folder."
else
  echo "One step is left, and it is the only one that needs the user — once per"
  echo "browser profile:"
  echo "  chrome://extensions -> Developer mode -> Load unpacked -> $EXTENSION_DIR"
  echo "  The card must then read $EXTENSION_ID; if it does not, the folder picked"
  echo "  was not this one."
  echo "After that, rerunning this script needs nothing from the user."
fi

if [[ -z "${CHROME_AGENT_HOME:-}" && -d "$LEGACY_RUNTIME_DIR" ]]; then
  echo
  echo "note: $LEGACY_RUNTIME_DIR is left over from an install that predates this"
  echo "      one, and nothing here reads it any more. Look before removing it: it is"
  echo "      not only this script's files. If an extension loaded from it is still at"
  echo "      chrome://extensions, remove that card and load $EXTENSION_DIR"
  echo "      instead — the old copy is not updated any more."
fi

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo
  echo "note: $BIN_DIR is not on PATH; invoke $BIN_DIR/chrome-agent or add it."
fi
