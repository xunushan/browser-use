"""Put the manual where the agent keeps skills, and nothing else there.

The skill directory used to be a symlink to the whole checkout, which made the
one directory an agent reads into a second copy of the project: runtime, tests,
caches, design docs. What that directory is for is narrower — it is how an agent
finds out how to drive this tool. So it is a real directory holding exactly the
manual, and this module is what keeps it in step with the checkout:

    <checkout>/SKILL.md            --sync_skill()-->  <skills>/chrome-agent/SKILL.md
    <checkout>/references/*.md     --sync_skill()-->  <skills>/chrome-agent/references/*.md

The runtime is not copied there. `chrome-agent` is a tool with an install home of
its own; the skill says how to use it, and reading the skill must not depend on
finding the checkout.

The file list is written out rather than globbed. A reference a reader is told to
open but that never got copied is a dead link in the manual, and the place to
notice that is a failing test, not a reader mid-task.
"""

import shutil
from pathlib import Path

# The `name:` in SKILL.md's frontmatter, and the directory name a skill is found
# under. setup.sh has always used the same string for both.
SKILL_NAME = "chrome-agent"

# What the manual is made of, relative to the checkout.
MANUAL_NAME = "SKILL.md"
REFERENCES_DIR = "references"
REFERENCE_NAMES = (
    "install-and-setup.md",
    "media-and-downloads.md",
    "site-exploration-and-playbook-spec.md",
    "troubleshooting.md",
)


def manual_files(source: Path) -> list[Path]:
    """Every file the manual is made of, relative to the checkout, in order."""
    paths = [Path(MANUAL_NAME)]
    paths.extend(Path(REFERENCES_DIR) / name for name in REFERENCE_NAMES)

    missing = [str(path) for path in paths if not (Path(source) / path).is_file()]
    if missing:
        raise FileNotFoundError(
            f"the manual at {source} is incomplete: missing {', '.join(missing)}"
        )
    return paths


def frontmatter(text: str) -> str:
    """The frontmatter block of a SKILL.md, or "" if it has none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index])
    return ""


def is_our_skill(target: Path) -> bool:
    """Whether this path holds the manual this module writes.

    Read through a symlink on purpose: the install this replaced left a link to
    the checkout, and that link is ours to remove even though the directory it
    resolves to lives somewhere else.
    """
    try:
        text = (Path(target) / MANUAL_NAME).read_text(encoding="utf-8")
    except OSError:
        return False
    return any(
        line.strip() == f"name: {SKILL_NAME}" for line in frontmatter(text).splitlines()
    )


def _refuse(target: Path, verb: str) -> FileExistsError:
    return FileExistsError(
        f"Refusing to {verb} {target}: it is not a {SKILL_NAME} skill. Use --force."
    )


def _clear(target: Path, force: bool) -> None:
    """Remove whatever is at the target path, once it is safe to.

    A symlink is checked before the same-directory guard below, because the
    install this replaced left exactly that: a link pointing at the checkout.
    Comparing the two after resolving would find them equal and leave the link.
    """
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        if not is_our_skill(target) and not force:
            raise _refuse(target, "replace")
        target.unlink()


def sync_skill(source: Path, target: Path, *, force: bool = False) -> list[str]:
    """Write the manual into a skill directory, and return what landed.

    Returns [] in the one case where doing nothing is right: the checkout is
    itself the skill directory. Copying there would delete the runtime, the
    extension and the install script to make room for four files, so that guard
    is about not destroying an install rather than about tidiness.
    """
    source, target = Path(source), Path(target)

    _clear(target, force)

    if target.is_dir() and source.resolve() == target.resolve():
        return []

    if target.exists() and not is_our_skill(target) and not force:
        raise _refuse(target, "replace")

    paths = manual_files(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".incoming")
    previous = target.with_name(target.name + ".previous")

    # Built beside the real one and swapped in, so a reader never opens a manual
    # that is halfway written. Same reasoning as the extension copy.
    shutil.rmtree(staging, ignore_errors=True)
    try:
        for relative in paths:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, destination)
        shutil.rmtree(previous, ignore_errors=True)
        if target.exists():
            target.rename(previous)
        staging.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)

    return [str(path) for path in paths]


def remove_skill(target: Path, *, force: bool = False) -> bool:
    """Delete the manual from a skill directory, and say whether anything went.

    Guarded like the sync: an unrelated directory at that path belongs to
    someone else, and removing the wrong small directory looks like a success.
    """
    target = Path(target)
    if not target.exists() and not target.is_symlink():
        return False
    if not is_our_skill(target) and not force:
        raise _refuse(target, "remove")

    if target.is_symlink():
        target.unlink()
    else:
        shutil.rmtree(target)
    return True


def skill_dirs(value: str) -> list[Path]:
    """Split a space-separated list of skill directories, as setup.sh passes it."""
    return [Path(part).expanduser() for part in value.split() if part]


def sync_skill_dirs(source: Path, dirs: list[Path], *, force: bool = False) -> list[str]:
    """Sync the manual into each skill directory, and return the ones written."""
    written = []
    for directory in dirs:
        target = Path(directory) / SKILL_NAME
        if sync_skill(source, target, force=force):
            written.append(str(target))
    return written
