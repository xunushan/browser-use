"""Routing a site to its Playbook, and the ID the manifest key pins.

Both exist to close a seam. Routing used to be a search over a path inside the
source tree, which stops resolving the moment the skill is installed anywhere
else — the normal case, since the skill is what gets linked into an agent's
skill directory. The extension ID used to be copied out of chrome://extensions
and passed to install.sh by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from chrome_agent import playbooks
from chrome_agent.cli.main import cli
from chrome_agent.utils.extension_id import extension_id, manifest_extension_id

REPO = Path(__file__).parent.parent
SKILL = REPO / "skill" / "chrome-agent"
MANIFEST = REPO / "extension" / "manifest.json"


@pytest.fixture
def routed(monkeypatch):
    """Resolve against the checkout, whatever this machine has installed."""
    monkeypatch.setenv(playbooks.SKILL_ENV, str(SKILL))


# --- finding the skill ---------------------------------------------------


def test_the_env_override_decides_where_the_skill_is(monkeypatch, tmp_path):
    """An explicit directory wins outright, not merely as a first candidate."""
    monkeypatch.setenv(playbooks.SKILL_ENV, str(tmp_path))
    (tmp_path / "SKILL.md").write_text("---\nname: chrome-agent\n---\n", encoding="utf-8")

    assert playbooks.skill_dir() == tmp_path


def test_the_checkout_is_used_when_nothing_is_installed(monkeypatch, tmp_path):
    """A developer running from the tree should not need install.sh first."""
    monkeypatch.delenv(playbooks.SKILL_ENV, raising=False)
    monkeypatch.setenv(playbooks.HOME_ENV, str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert playbooks.skill_dir() == SKILL


def test_a_broken_skill_directory_says_where_it_looked(monkeypatch, tmp_path):
    monkeypatch.setenv(playbooks.SKILL_ENV, str(tmp_path / "absent"))

    with pytest.raises(FileNotFoundError) as error:
        playbooks.all_playbooks()

    assert "SKILL.md" in str(error.value)
    assert str(tmp_path / "absent") in str(error.value)


# --- routing -------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("xiaohongshu.com", "xiaohongshu.com"),
        ("www.xiaohongshu.com", "xiaohongshu.com"),
        ("https://www.xiaohongshu.com/explore/6ac4?xsec_token=x", "xiaohongshu.com"),
        ("http://WWW.Xiaohongshu.COM", "xiaohongshu.com"),
    ],
)
def test_the_registrable_domain_survives_urls_and_case(target, expected):
    assert playbooks.registrable_domain(target) == expected


def test_a_domain_that_is_not_a_domain_is_refused():
    with pytest.raises(ValueError):
        playbooks.registrable_domain("   ")


def test_a_site_is_found_by_its_domain(routed):
    found = playbooks.match("xiaohongshu.com")

    assert [entry.site for entry in found] == ["xiaohongshu"]
    assert found[0].path.is_file()
    assert found[0].directory == found[0].path.parent


def test_an_unknown_site_matches_nothing(routed):
    assert playbooks.match("example.com") == []


def test_listing_finds_every_installed_playbook(routed):
    assert [entry.site for entry in playbooks.all_playbooks()] == ["xiaohongshu"]


# --- the command the skill tells an agent to run -------------------------


def test_the_command_prints_the_playbook_to_read(routed):
    result = CliRunner().invoke(cli, ["playbook", "--domain", "xiaohongshu.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["domain"] == "xiaohongshu.com"
    assert payload["playbooks"][0]["site"] == "xiaohongshu"
    assert Path(payload["playbooks"][0]["path"]).is_file()


def test_the_command_prints_the_site_directory_on_request(routed):
    result = CliRunner().invoke(cli, ["playbook", "--domain", "xiaohongshu.com", "--dir"])

    assert result.exit_code == 0, result.output
    directory = Path(result.output.strip())
    assert (directory / "PLAYBOOK.md").is_file()
    assert (directory / "scripts").is_dir()


def test_an_uncovered_domain_exits_non_zero(routed):
    result = CliRunner().invoke(cli, ["playbook", "--domain", "example.com"])

    assert result.exit_code == 1
    assert "example.com" in result.output


def test_the_command_asks_for_something_to_do(routed):
    result = CliRunner().invoke(cli, ["playbook"])

    assert result.exit_code == 2
    assert "--domain" in result.output


# --- the extension ID the manifest pins ---------------------------------


def test_the_id_follows_chromium():
    """SHA256, first 16 bytes as hex, then 0-f shifted to a-p.

    The expectation was computed separately (openssl for the digest, an explicit
    translation table for the alphabet), and the whole rule was checked against
    a real ID: hashing the path of an unpacked extension reproduces the ID
    Chrome shows for it.
    """
    assert extension_id("aGVsbG8=") == "cmpcenlkfplakdaocgoidlckmfljocjo"
    assert extension_id("Y2hyb21lLWFnZW50") == "jmimmbkgeldngcanlcobhighhmmiligb"


def test_unpadded_and_wrapped_keys_decode_alike():
    assert extension_id("aGVsbG8") == extension_id("aGVs bG8=\n")


def test_the_shipped_manifest_pins_an_id():
    identifier = manifest_extension_id(MANIFEST)

    assert identifier is not None
    assert len(identifier) == 32
    assert set(identifier) <= set("abcdefghijklmnop")
    # Without a key Chrome would derive the ID from the directory path instead,
    # so a pinned ID must not look like one.
    assert identifier != "ljddnkahpmiaklkfhimhandipjhpknmj"


def test_a_manifest_without_a_key_pins_nothing(tmp_path):
    keyless = tmp_path / "manifest.json"
    keyless.write_text('{"manifest_version": 3}', encoding="utf-8")

    assert manifest_extension_id(keyless) is None
