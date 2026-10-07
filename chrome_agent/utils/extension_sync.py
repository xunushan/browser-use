"""Keep the copy of the extension that Chrome loaded where an update cannot break it.

Chrome remembers the directory an unpacked extension was loaded from, and if
that directory disappears the extension stops working and has to be loaded again
by hand. The checkout is where the extension is written, not where it is loaded
from, so the copy Chrome loads lives in the install home instead, and setup
keeps the two in step:

    <checkout>/extension  --sync_extension()-->  ~/chrome-agent/extension

The hash of what was written is recorded in install.json, and it is recorded
only once the extension confirms it reloaded: a hash written on the strength of
the copy alone would call a failed reload a success.
"""

import hashlib
import json
import shutil
from pathlib import Path

# Left behind by a copy or a run, and not part of the extension.
IGNORED_NAMES = (".DS_Store", "__pycache__")


def _files(root: Path) -> list[Path]:
    """Every file that belongs to the extension, in a stable order."""
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in IGNORED_NAMES for part in path.relative_to(root).parts)
    )


def tree_hash(root: Path) -> str:
    """Hash the directory's file names and contents, so a copy compares equal."""
    digest = hashlib.sha256()
    for path in _files(root):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def sync_extension(source: Path, destination: Path) -> str:
    """Mirror source onto destination, and return the hash of what landed.

    The new copy is built beside the old one and swapped in, so the directory
    Chrome points at is never missing, not even for the moment it would take to
    unpack it in place.
    """
    if not source.is_dir():
        raise FileNotFoundError(f"no extension to sync at {source}")

    staging = destination.with_name(destination.name + ".incoming")
    previous = destination.with_name(destination.name + ".previous")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        shutil.copytree(source, staging, ignore=shutil.ignore_patterns(*IGNORED_NAMES))
        shutil.rmtree(previous, ignore_errors=True)
        if destination.exists():
            destination.rename(previous)
        staging.rename(destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)
    return tree_hash(destination)


def recorded_hash(record_path: Path) -> str | None:
    """Get the hash of the extension the user last loaded, if it was recorded."""
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = record.get("extensionHash")
    return value if isinstance(value, str) else None


def record_hash(record_path: Path, value: str) -> None:
    """Record the hash of a copy the extension confirmed it reloaded to."""
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    record["extensionHash"] = value
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
