"""The skill is this repository, and it is generic.

The skill ships the whole tool — runtime, extension, install script — so that an
agent that finds it needs nothing else. What it must not ship is site knowledge:
a website's containers, selectors and measurements belong to that website's own
skill, which drives this one through the CLI. The marker scan below is how that
stays true.
"""

from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
SKILL = SKILL_DIR / "SKILL.md"

REFERENCES = [
    "install-and-setup.md",
    "site-exploration-and-playbook-spec.md",
    "media-and-downloads.md",
    "troubleshooting.md",
]

# A site name, one site's class names, or an observation measured on a single
# site appearing in the generic part of the skill means something was filed in
# the wrong place.
SITE_MARKERS = ("xiaohongshu", "小红书", "xhs", "note-text", "comment-", "xsec", "轮播")

GENERIC_FILES = [SKILL, *sorted((SKILL_DIR / "references").glob("*.md"))]


def test_the_skill_ships_the_whole_tool():
    """Install = put this directory where the agent keeps skills, and nothing else.

    If the runtime or the extension lived outside the skill, installing would
    mean assembling pieces from two places again.
    """
    for relative in ("chrome_agent", "extension/manifest.json", "setup.sh"):
        assert (SKILL_DIR / relative).exists(), relative


def test_project_skill_exposes_generic_browser_workflow():
    content = SKILL.read_text(encoding="utf-8")
    assert "chrome-agent ensure" in content
    assert "chrome-agent tabs navigate" in content
    assert "chrome-agent page snapshot" in content
    assert "chrome-agent page text" in content
    assert "Snapshot element text is intentionally capped at 200 characters" in content
    # The media commands are named in the surface list, with the prefix stated
    # once above it rather than repeated on every row.
    assert "page media" in content
    assert "page download-media" in content
    assert "chrome-agent <group> <command>" in content
    assert "xiaohongshu collect" not in content


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


def test_the_interface_contract_names_the_cli_and_nothing_else():
    """A site skill may depend on the command surface; that is the whole contract."""
    content = SKILL.read_text(encoding="utf-8")
    section = content.split("## 4. What a site skill may depend on", 1)[1].split("## 5.", 1)[0]

    assert "chrome-agent" in section
    assert "Do not import `chrome_agent`" in section
    assert "--json" in section


def test_no_site_specific_content_in_the_generic_skill():
    """Site content goes to that site's own skill, not here."""
    for path in GENERIC_FILES:
        text = path.read_text(encoding="utf-8").lower()
        found = [marker for marker in SITE_MARKERS if marker in text]
        assert not found, f"{path.name} 含站点专属内容：{found}"
