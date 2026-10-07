"""Keeping the copy Chrome loads in step with the source in the checkout.

Chrome remembers the directory an unpacked extension was loaded from, so the
copy it points at must survive a checkout that moves. These tests cover the two
things that make that safe: the copy is a faithful mirror, and what landed can
be compared against what the extension last confirmed.
"""

import json
import platform
from pathlib import Path

import pytest

from chrome_agent.utils.extension_sync import (
    record_hash,
    recorded_hash,
    sync_extension,
    tree_hash,
)
from chrome_agent.utils.paths import get_extension_dir, get_home_dir, get_socket_path


def make_extension(root: Path, marker: str = "one") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text('{"name": "Chrome Agent"}', encoding="utf-8")
    (root / "icons").mkdir(exist_ok=True)
    (root / "icons" / "icon16.png").write_bytes(b"\x89PNG" + marker.encode())
    return root


class TestTreeHash:
    def test_hash_is_stable_across_walks(self, tmp_path):
        """Two readings of an unchanged tree must compare equal."""
        source = make_extension(tmp_path / "source")

        assert tree_hash(source) == tree_hash(source)

    def test_content_change_changes_the_hash(self, tmp_path):
        source = make_extension(tmp_path / "source")
        before = tree_hash(source)

        (source / "background.js").write_text("// new", encoding="utf-8")

        assert tree_hash(source) != before

    def test_a_rename_alone_changes_the_hash(self, tmp_path):
        """File names are part of what the extension is, not just their bytes."""
        source = make_extension(tmp_path / "source")
        before = tree_hash(source)

        (source / "popup.js").write_text("// same bytes either way", encoding="utf-8")
        first = tree_hash(source)
        (source / "popup.js").rename(source / "popup2.js")

        assert first != before
        assert tree_hash(source) != first

    def test_a_copy_hashes_like_its_source(self, tmp_path):
        """The comparison that decides on a reload relies on this."""
        source = make_extension(tmp_path / "source")
        destination = tmp_path / "destination"

        landed = sync_extension(source, destination)

        assert landed == tree_hash(source) == tree_hash(destination)

    def test_editor_leftovers_are_not_content(self, tmp_path):
        """.DS_Store is the Finder's, not the extension's, and must not count."""
        source = make_extension(tmp_path / "source")
        before = tree_hash(source)

        (source / ".DS_Store").write_bytes(b"junk")
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "x.pyc").write_bytes(b"junk")

        assert tree_hash(source) == before


class TestSyncExtension:
    def test_sync_is_idempotent(self, tmp_path):
        source = make_extension(tmp_path / "source")
        destination = tmp_path / "destination"

        first = sync_extension(source, destination)
        second = sync_extension(source, destination)

        assert first == second
        assert (destination / "manifest.json").is_file()

    def test_a_second_sync_replaces_what_was_there(self, tmp_path):
        """The stale file is the failure mode this whole copy exists to prevent."""
        source = make_extension(tmp_path / "source")
        destination = tmp_path / "destination"
        sync_extension(source, destination)

        (source / "manifest.json").write_text('{"name": "Chrome Agent 2"}', encoding="utf-8")
        landed = sync_extension(source, destination)

        assert json.loads((destination / "manifest.json").read_text())["name"] == "Chrome Agent 2"
        assert landed == tree_hash(source)

    def test_no_staging_directories_are_left_behind(self, tmp_path):
        """The swap is meant to be invisible, not to litter the parent."""
        source = make_extension(tmp_path / "source")
        destination = tmp_path / "destination"

        sync_extension(source, destination)

        assert sorted(p.name for p in tmp_path.iterdir()) == ["destination", "source"]

    def test_missing_source_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            sync_extension(tmp_path / "nope", tmp_path / "destination")


class TestInstallHome:
    """Where the copy lands is load-bearing, and only a person can see why.

    Loading the extension by hand is the one step of the install Chrome does not
    provide a way around, and macOS file dialogs do not list dot directories: an
    install home called `~/.chrome-agent` cannot be picked in that dialog at all.
    Nothing in the code would notice a rename back, so the name is asserted here.
    """

    def test_the_home_is_a_directory_a_file_dialog_shows(self, monkeypatch):
        monkeypatch.delenv("CHROME_AGENT_HOME", raising=False)

        assert not get_home_dir().name.startswith(".")
        assert not get_extension_dir().name.startswith(".")

    def test_the_home_can_be_pointed_elsewhere(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROME_AGENT_HOME", str(tmp_path / "elsewhere"))

        assert get_home_dir() == tmp_path / "elsewhere"
        assert get_extension_dir() == tmp_path / "elsewhere" / "extension"

    @pytest.mark.skipif(
        platform.system() == "Linux", reason="Linux keeps the socket in XDG_RUNTIME_DIR"
    )
    def test_the_socket_moves_with_the_home(self, tmp_path, monkeypatch):
        """One home, not a second dot directory beside it holding the socket."""
        monkeypatch.setenv("CHROME_AGENT_HOME", str(tmp_path / "home"))

        assert get_socket_path() == tmp_path / "home" / "run" / "daemon.sock"


class TestInstallRecord:
    def test_hash_round_trips(self, tmp_path):
        record = tmp_path / "install.json"
        record.write_text('{"version": "0.1.0"}', encoding="utf-8")

        record_hash(record, "abc123")

        assert recorded_hash(record) == "abc123"
        # The rest of the record is not this function's to lose.
        assert json.loads(record.read_text())["version"] == "0.1.0"

    def test_no_record_reads_as_unknown(self, tmp_path):
        """Unknown has to be distinguishable from "does not match"."""
        assert recorded_hash(tmp_path / "absent.json") is None

    def test_a_record_without_a_hash_reads_as_unknown(self, tmp_path):
        record = tmp_path / "install.json"
        record.write_text('{"version": "0.1.0"}', encoding="utf-8")

        assert recorded_hash(record) is None

    def test_a_corrupt_record_reads_as_unknown(self, tmp_path):
        record = tmp_path / "install.json"
        record.write_text("{not json", encoding="utf-8")

        assert recorded_hash(record) is None

    def test_recording_onto_a_corrupt_record_still_works(self, tmp_path):
        record = tmp_path / "install.json"
        record.write_text("{not json", encoding="utf-8")

        record_hash(record, "abc123")

        assert recorded_hash(record) == "abc123"
