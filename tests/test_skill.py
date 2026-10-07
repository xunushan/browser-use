"""The manual is generic, and it is the whole of what a skill directory holds.

`setup.sh` writes SKILL.md and the references into the agent's skill directory
and nothing else — see `chrome_agent/utils/skill_sync.py` — so what an agent
finds there describes the tool instead of being the tool. What the manual must
never carry is site knowledge: a website's containers, selectors and
measurements belong to that website's own skill, which drives this one through
the CLI. The marker scan below is how that stays true, and it covers the code as
well as the prose: the manifest is the one place a site could be named and
silently authorized.

The surface block is the other half of that contract, in the other direction: it
is what an agent copies into a shell, so every name in it has to be a command the
CLI answers to. One test here reads the block and asks the CLI.

These tests read the checkout, which is where the manual is written.
"""

import os
import re
import site
import subprocess
import sys
from pathlib import Path

from chrome_agent.utils.skill_sync import REFERENCE_NAMES

SKILL_DIR = Path(__file__).parent.parent
SKILL = SKILL_DIR / "SKILL.md"

# The same list `setup.sh` copies, so the two cannot drift apart.
REFERENCES = list(REFERENCE_NAMES)

# A site name, one site's class names, or an observation measured on a single
# site appearing in the generic part of the skill means something was filed in
# the wrong place.
SITE_MARKERS = ("xiaohongshu", "小红书", "xhs", "note-text", "comment-", "xsec", "轮播")

# What a site name can hide in. Binaries — icons — are not read.
TEXT_SUFFIXES = (".js", ".json", ".py", ".md", ".html", ".sh")


def generic_files() -> list[Path]:
    """Everything that has to stay free of site knowledge.

    The scan used to cover the prose alone, which is exactly why a site name
    survived in the manifest and in a content script. `tests/` is left out: the
    site names there are fixtures for this repository's own behaviour.
    """
    files = [SKILL, *sorted((SKILL_DIR / "references").glob("*.md"))]
    for root in (SKILL_DIR / "extension", SKILL_DIR / "chrome_agent"):
        files.extend(
            path for path in sorted(root.rglob("*")) if path.suffix in TEXT_SUFFIXES
        )
    files.append(SKILL_DIR / "setup.sh")
    return [path for path in files if path.is_file()]


def test_every_reference_written_here_is_one_the_skill_ships():
    """The copy list is written out, so a new reference has to be added to it.

    Globbing would ship a file nobody was told to read; a list with a stale entry
    would leave a link in the manual pointing at nothing. Both are caught here,
    against the checkout the copy is taken from.
    """
    written = sorted(path.name for path in (SKILL_DIR / "references").glob("*.md"))

    assert written == sorted(REFERENCES)


def test_project_skill_exposes_generic_browser_workflow():
    content = SKILL.read_text(encoding="utf-8")
    assert "chrome-agent extension status" in content
    assert "chrome-agent tabs navigate" in content
    assert "chrome-agent page snapshot" in content
    assert "chrome-agent page text" in content
    assert "Snapshot element text is intentionally capped at 200 characters" in content
    # The media commands are named in the surface list, with the prefix stated
    # once above it rather than repeated on every row.
    assert "download-images" in content
    assert "download-media" in content
    assert "chrome-agent <group> <command>" in content
    assert "xiaohongshu collect" not in content


def test_the_command_surface_is_listed_by_group():
    """The surface is what an agent copies from, so it has to be literal.

    It used to file the commands under invented headings — `service:`,
    `observe:`, `media:` — above a line claiming every command was
    `chrome-agent <group> <command>`. An agent read the heading as a group name
    and ran `chrome-agent service version`, which answers "No such command".
    The three real groups and the standalone commands are asserted as the CLI
    spells them, and the old headings are asserted gone.
    """
    surface = SKILL.read_text(encoding="utf-8").split("```text", 1)[1].split("```", 1)[0]
    lines = [line for line in surface.splitlines() if line.strip()]

    for group in ("extension", "page", "sites", "tabs"):
        assert any(line.startswith(f"chrome-agent {group} ") for line in lines), group
    standalone = [line for line in lines if line.startswith("chrome-agent ")]
    assert any("ensure" in line for line in standalone), "standalone commands"
    for invented in ("service", "install", "observe", "act", "media"):
        assert not any(line.startswith(f"{invented}:") for line in lines), invented


def cli_help(*args: str, home: Path) -> str:
    """Run `chrome-agent <args> --help` against an empty HOME, and return it.

    An empty HOME is a machine with no daemon and no runtime directory, which is
    the point: `--help` must not need one, and this must not disturb the real
    installation. Dependencies live in the real HOME's user site-packages, so
    that path has to be carried over or the import fails before `--help` runs.
    """
    env = {**os.environ, "HOME": str(home)}
    env["PYTHONPATH"] = os.pathsep.join(
        [site.getusersitepackages(), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-m", "chrome_agent.cli", *args, "--help"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"chrome-agent {' '.join(args)} --help failed: {result.stderr}"
    return result.stdout


def command_names(help_text: str) -> set[str]:
    """The command names a help page lists."""
    if "Commands:" not in help_text:
        return set()
    block = help_text.split("Commands:", 1)[1]
    names = set()
    for line in block.splitlines():
        match = re.match(r"^  ([a-z][a-z-]*)\s{2,}\S", line)
        if match:
            names.add(match.group(1))
        elif line.strip() and not line.startswith(" "):
            break
    return names


def test_every_command_the_surface_names_exists(tmp_path):
    """A name the CLI does not answer to is a dead end found mid-task.

    This is the bug the surface has already shipped once: it filed commands
    under invented headings that read as group names, and the first command an
    agent copied out of it — `chrome-agent service version` — was answered with
    "No such command 'service'".
    """
    surface = SKILL.read_text(encoding="utf-8").split("```text", 1)[1].split("```", 1)[0]
    home = tmp_path / "home"
    home.mkdir()
    top_level = command_names(cli_help(home=home))
    subcommands = {group: command_names(cli_help(group, home=home)) for group in top_level}

    rows = [row for row in surface.splitlines() if row.strip()]
    assert rows, "the surface block is empty"
    for row in rows:
        # Every line is a command someone can paste, spelled the way it runs.
        # The headings this block used to carry (`service: ensure | status`)
        # were read as commands, so a line that is not one is itself the bug.
        assert row.startswith("chrome-agent "), f"not a command line: {row!r}"
        fields = row[len("chrome-agent") :].split("|")
        head = fields[0].split()
        # `chrome-agent page  snapshot | extract` names a group and its first
        # command; `chrome-agent  ensure | status` names standalone commands.
        if len(head) == 2:
            group, first = head
            assert group in top_level, f"surface names unknown group {group!r}"
            listed = [first, *(field.split()[0] for field in fields[1:])]
            for name in listed:
                assert name in subcommands[group], f"{group} has no command {name!r}"
        else:
            assert len(head) == 1, row
            for field in fields:
                name = field.split()[0]
                assert name in top_level, f"unknown top-level command {name!r}"


def test_the_body_stays_short_enough_to_read_every_time():
    """The whole point of moving the long flows out is that this file is cheap."""
    content = SKILL.read_text(encoding="utf-8")

    assert len(content.splitlines()) <= 130


def test_the_references_are_listed_and_exist():
    """A reference nobody is told to read may as well not exist."""
    content = SKILL.read_text(encoding="utf-8")

    for name in REFERENCES:
        assert (SKILL_DIR / "references" / name).is_file(), name
        assert f"references/{name}" in content, name


def test_every_reference_is_linked_to_from_the_read_on_demand_table():
    content = SKILL.read_text(encoding="utf-8")
    table = content.split("## Read on demand", 1)[1].split("## 0.", 1)[0]

    for name in REFERENCES:
        assert f"references/{name}" in table, name


def test_the_install_section_hands_off_to_the_manual():
    """An agent that has never run this needs both the script and the one click."""
    content = SKILL.read_text(encoding="utf-8")
    section = content.split("## 0. Install", 1)[1].split("## 1.", 1)[0]

    assert "setup.sh" in section
    assert "references/install-and-setup.md" in section
    assert "chrome://extensions" in section


def test_the_install_section_checks_before_it_installs():
    """The failure this prevents is being told to reload what is already loaded.

    A skill update must not read as an extension reinstall: the command existing
    is the answer, and only a disconnected extension is worth acting on.
    """
    content = SKILL.read_text(encoding="utf-8")
    section = content.split("## 0. Install", 1)[1].split("## 1.", 1)[0]

    assert "chrome-agent extension status" in section
    assert "connected: false" in section
    assert "install nothing" in section
    assert "no update and no reinstall needs the extension" in section


def test_no_site_specific_content_in_the_generic_skill():
    """Site content goes to that site's own skill, not here."""
    for path in generic_files():
        text = path.read_text(encoding="utf-8").lower()
        found = [marker for marker in SITE_MARKERS if marker in text]
        assert not found, f"{path.name} 含站点专属内容：{found}"


def test_the_interface_contract_names_the_cli_and_nothing_else():
    """A site skill may depend on the command surface; that is the whole contract."""
    content = SKILL.read_text(encoding="utf-8")
    section = content.split("## 4. What a site skill may depend on", 1)[1].split("## 5.", 1)[0]

    assert "chrome-agent" in section
    assert "Do not import `chrome_agent`" in section
    assert "--json" in section
