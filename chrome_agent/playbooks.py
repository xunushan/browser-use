"""Find the Playbook that covers a site.

A Playbook is the site-specific half of a task: which container holds the body,
how far to scroll, how to tell that a click really landed. Playbooks ship inside
the skill bundle, under `sites/<site>/`, next to the `SKILL.md` that routes to
them.

That routing has to survive installation. A search over a path in the source
tree stops resolving the moment the skill is installed elsewhere — which is the
normal case, since the skill is what gets linked into an agent's skill
directory. So the route is resolved from wherever the skill actually is:
`chrome-agent playbook` prints it, and this module is what that command reads.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

SKILL_ENV = "CHROME_AGENT_SKILL_DIR"
HOME_ENV = "CHROME_AGENT_HOME"
SKILL_NAME = "chrome-agent"
SKILL_MARKER = "SKILL.md"
SITES_DIRNAME = "sites"
PLAYBOOK_FILENAME = "PLAYBOOK.md"


@dataclass(frozen=True)
class Playbook:
    site: str
    path: Path

    @property
    def directory(self) -> Path:
        return self.path.parent


def home() -> Path:
    """The runtime directory the installer writes its record into."""
    configured = os.environ.get(HOME_ENV)
    return Path(configured).expanduser() if configured else Path.home() / ".chrome-agent"


def install_record() -> dict[str, object]:
    """What the installer recorded, or an empty mapping if it has not run."""
    record = home() / "install.json"
    if not record.is_file():
        return {}
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def candidate_skill_dirs() -> list[Path]:
    """Every place the skill may live, most explicit first.

    `CHROME_AGENT_SKILL_DIR` is exclusive rather than merely first: asking for a
    specific directory and silently getting another one is worse than an error.
    """
    override = os.environ.get(SKILL_ENV)
    if override:
        return [Path(override).expanduser()]
    candidates: list[Path] = []
    recorded = install_record().get("skillDir")
    if isinstance(recorded, str) and recorded:
        candidates.append(Path(recorded).expanduser())
    candidates.append(Path.home() / ".claude" / "skills" / SKILL_NAME)
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    candidates.append(codex_home / "skills" / SKILL_NAME)
    # Running from a checkout, with nothing installed yet.
    candidates.append(Path(__file__).resolve().parent.parent / "skill" / SKILL_NAME)
    return candidates


def skill_dir() -> Path | None:
    for candidate in candidate_skill_dirs():
        if (candidate / SKILL_MARKER).is_file():
            return candidate
    return None


def sites_dir() -> Path:
    found = skill_dir()
    if found is None:
        looked = "\n".join(f"  {path}" for path in candidate_skill_dirs())
        raise FileNotFoundError(
            f"没找到 chrome-agent skill（缺 {SKILL_MARKER}）。找过：\n{looked}\n"
            f"先运行 install.sh，或用 {SKILL_ENV} 指定 skill 目录。"
        )
    sites = found / SITES_DIRNAME
    if not sites.is_dir():
        raise FileNotFoundError(f"{found} 下没有 {SITES_DIRNAME}/ 目录")
    return sites


def all_playbooks() -> list[Playbook]:
    """Every installed Playbook, by site directory name."""
    return [
        Playbook(path.parent.name, path)
        for path in sorted(sites_dir().glob(f"*/{PLAYBOOK_FILENAME}"))
    ]


def registrable_domain(target: str) -> str:
    """`https://www.xiaohongshu.com/explore/1` and `xiaohongshu.com` alike."""
    candidate = target.strip()
    if "//" not in candidate:
        candidate = f"//{candidate}"
    host = (urlsplit(candidate).hostname or "").lower()
    host = host.removeprefix("www.")
    if not host:
        raise ValueError(f"无法从 {target!r} 解析出域名")
    return host


def match(domain: str) -> list[Playbook]:
    """Playbooks whose PLAYBOOK.md names this domain."""
    wanted = domain.lower()
    return [
        playbook
        for playbook in all_playbooks()
        if wanted in playbook.path.read_text(encoding="utf-8").lower()
    ]
