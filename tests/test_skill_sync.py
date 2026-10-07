"""What the agent's skill directory is allowed to contain.

The skill directory used to be a symlink to the whole checkout, so an agent
opening it found a project. It holds the manual now, and these tests are the
statement of that: four reference files and SKILL.md, no runtime, no extension,
no install script — and none of them lost on the way.
"""

from pathlib import Path

import pytest

from chrome_agent.utils.skill_sync import (
    MANUAL_NAME,
    REFERENCE_NAMES,
    REFERENCES_DIR,
    SKILL_NAME,
    is_our_skill,
    manual_files,
    remove_skill,
    sync_skill,
    sync_skill_dirs,
)


def checkout(root: Path) -> Path:
    """A checkout in miniature: the manual, plus everything that must not ship.

    The extra files are the point. A copy that walks the tree would pass a test
    that only looked for SKILL.md.
    """
    source = root / "checkout"
    (source / REFERENCES_DIR).mkdir(parents=True)
    (source / MANUAL_NAME).write_text(
        f"---\nname: {SKILL_NAME}\ndescription: d\n---\n\n# Manual\n", encoding="utf-8"
    )
    for name in REFERENCE_NAMES:
        (source / REFERENCES_DIR / name).write_text(f"# {name}\n", encoding="utf-8")

    (source / "chrome_agent").mkdir()
    (source / "chrome_agent" / "__init__.py").write_text("", encoding="utf-8")
    (source / "extension").mkdir()
    (source / "extension" / "manifest.json").write_text("{}", encoding="utf-8")
    (source / "setup.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests" / "test_whatever.py").write_text("", encoding="utf-8")
    return source


def installed(target: Path) -> set[str]:
    """Every file under a skill directory, as relative paths."""
    return {str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()}


def test_only_the_manual_is_copied(tmp_path):
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME

    sync_skill(source, target)

    expected = {MANUAL_NAME} | {f"{REFERENCES_DIR}/{name}" for name in REFERENCE_NAMES}
    assert installed(target) == expected


def test_the_runtime_and_the_extension_are_not_copied(tmp_path):
    """The tool has an install home; reading the skill must not need the checkout."""
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME

    sync_skill(source, target)

    for absent in ("setup.sh", "chrome_agent/__init__.py", "extension/manifest.json"):
        assert not (target / absent).exists(), absent


def test_the_copied_manual_is_the_checkout_one(tmp_path):
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME

    sync_skill(source, target)

    for relative in manual_files(source):
        assert (target / relative).read_bytes() == (source / relative).read_bytes()


def test_a_symlink_to_the_checkout_becomes_a_real_directory(tmp_path):
    """The install this replaced left exactly this, and it has to be migrated.

    A guard that compared the two paths after resolving them would call the link
    and its target the same directory and leave the link in place.
    """
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME
    target.parent.mkdir(parents=True)
    target.symlink_to(source)

    sync_skill(source, target)

    assert not target.is_symlink()
    assert target.is_dir()
    assert installed(target) == {
        MANUAL_NAME,
        *{f"{REFERENCES_DIR}/{name}" for name in REFERENCE_NAMES},
    }
    # The checkout is untouched by the migration.
    assert (source / "setup.sh").exists()


def test_an_unrelated_directory_is_left_alone(tmp_path):
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME
    target.mkdir(parents=True)
    (target / MANUAL_NAME).write_text("---\nname: something-else\n---\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not a chrome-agent skill"):
        sync_skill(source, target)

    assert (target / MANUAL_NAME).read_text(encoding="utf-8").startswith("---\nname: something")


def test_force_replaces_an_unrelated_directory(tmp_path):
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME
    target.mkdir(parents=True)
    (target / MANUAL_NAME).write_text("---\nname: something-else\n---\n", encoding="utf-8")

    sync_skill(source, target, force=True)

    assert is_our_skill(target)


def test_nothing_happens_when_the_checkout_is_the_skill_directory(tmp_path):
    """Copying here would delete the runtime to make room for four files."""
    source = checkout(tmp_path)

    assert sync_skill(source, source) == []

    assert (source / "setup.sh").exists()
    assert (source / "chrome_agent" / "__init__.py").exists()
    assert (source / "extension" / "manifest.json").exists()


def test_a_second_sync_leaves_no_staging_behind(tmp_path):
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME

    sync_skill(source, target)
    sync_skill(source, target)

    assert sorted(path.name for path in target.parent.iterdir()) == [SKILL_NAME]


def test_a_reference_that_was_not_copied_is_an_error(tmp_path):
    """The list is written out, so a new reference cannot be silently skipped."""
    source = checkout(tmp_path)
    (source / REFERENCES_DIR / REFERENCE_NAMES[0]).unlink()

    with pytest.raises(FileNotFoundError, match="incomplete"):
        sync_skill(source, tmp_path / "skills" / SKILL_NAME)


def test_remove_takes_the_manual_away(tmp_path):
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME
    sync_skill(source, target)

    assert remove_skill(target) is True
    assert not target.exists()


def test_remove_clears_a_leftover_symlink(tmp_path):
    source = checkout(tmp_path)
    target = tmp_path / "skills" / SKILL_NAME
    target.parent.mkdir(parents=True)
    target.symlink_to(source)

    assert remove_skill(target) is True

    assert not target.is_symlink()
    assert source.exists()


def test_remove_refuses_a_directory_that_is_not_ours(tmp_path):
    target = tmp_path / "skills" / SKILL_NAME
    target.mkdir(parents=True)
    (target / MANUAL_NAME).write_text("---\nname: something-else\n---\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        remove_skill(target)

    assert target.exists()


def test_remove_says_so_when_there_was_nothing_there(tmp_path):
    assert remove_skill(tmp_path / "skills" / SKILL_NAME) is False


def test_every_skill_directory_is_written(tmp_path):
    source = checkout(tmp_path)
    dirs = [tmp_path / "one", tmp_path / "two"]

    written = sync_skill_dirs(source, dirs)

    assert sorted(written) == [str(directory / SKILL_NAME) for directory in dirs]
    for directory in dirs:
        assert is_our_skill(directory / SKILL_NAME)
