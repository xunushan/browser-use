import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent / "skill" / "chrome-agent"
SKILL = SKILL_DIR / "SKILL.md"

REFERENCES = [
    "site-exploration-and-playbook-spec.md",
    "media-and-downloads.md",
    "troubleshooting.md",
]

# Site-specific knowledge belongs in sites/<site>/PLAYBOOK.md. A site name, one
# site's class names, or an observation measured on a single site appearing in
# the generic part of the skill means something was filed in the wrong place.
SITE_MARKERS = ("xiaohongshu", "小红书", "xhs", "note-text", "comment-", "xsec", "轮播")

# SKILL.md and references/ are the generic skill; sites/ is where site content
# is supposed to be, so the marker scan covers only the former.
GENERIC_FILES = [SKILL]


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
    table = content.split("## Read on demand", 1)[1].split("## 1.", 1)[0]

    for name in REFERENCES:
        assert f"references/{name}" in table, name


def test_the_read_on_demand_table_points_at_site_playbooks():
    content = SKILL.read_text(encoding="utf-8")
    table = content.split("## Read on demand", 1)[1].split("## 1.", 1)[0]

    assert "PLAYBOOK.md" in table
    assert "section 4" in table


def test_no_site_specific_content_in_the_generic_skill():
    """Site content goes to sites/<site>/PLAYBOOK.md, not here."""
    generic = GENERIC_FILES + sorted((SKILL_DIR / "references").glob("*.md"))
    for path in generic:
        text = path.read_text(encoding="utf-8").lower()
        found = [marker for marker in SITE_MARKERS if marker in text]
        assert not found, f"{path.name} 含站点专属内容：{found}"


def test_playbooks_are_routed_to_by_registrable_domain():
    """The route is a command, not a path: the skill is installed elsewhere."""
    content = SKILL.read_text(encoding="utf-8")

    assert re.search(r"registrable domain", content)
    assert "chrome-agent playbook --domain" in content


def test_every_site_directory_has_a_playbook():
    sites = SKILL_DIR / "sites"

    assert sites.is_dir()
    for site in sorted(sites.iterdir()):
        assert (site / "PLAYBOOK.md").is_file(), site.name
