from pathlib import Path


def test_project_skill_exposes_generic_browser_workflow():
    skill = Path(__file__).parent.parent / ".agents" / "skills" / "chrome-agent" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "chrome-agent ensure" in content
    assert "chrome-agent tabs navigate" in content
    assert "chrome-agent page snapshot" in content
    assert "chrome-agent page text" in content
    assert "Snapshot element text is intentionally capped at 200 characters" in content
    assert "chrome-agent page media" in content
    assert "chrome-agent page download-media" in content
    assert "xiaohongshu collect" not in content
