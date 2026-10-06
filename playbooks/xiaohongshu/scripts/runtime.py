"""Configuration-driven snapshot helpers for the Xiaohongshu Playbook."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

PLAYBOOK_DIR = Path(__file__).resolve().parents[1]

NOTE_ID_RE = re.compile(r"/(?:explore|search_result|discovery/item)/([0-9a-f]{24})")


def note_id(url: str | None) -> str | None:
    """Extract the note ID from any of Xiaohongshu's note URL shapes."""
    match = NOTE_ID_RE.search(url or "")
    return match.group(1) if match else None


def load_locators() -> dict:
    with (PLAYBOOK_DIR / "locators.yaml").open(encoding="utf-8") as source:
        return yaml.safe_load(source)


def _class_names(element: dict) -> set[str]:
    return set(str(element.get("className") or "").split())


def matches(element: dict, rule: dict) -> bool:
    if rule.get("tag") and element.get("tag") != rule["tag"]:
        return False
    classes = _class_names(element)
    if any(name not in classes for name in rule.get("class_contains", [])):
        return False
    visible = bool(element.get("states", {}).get("visible"))
    if rule.get("visible") is not None and visible != rule["visible"]:
        return False
    rect = element.get("rect") or {}
    if rect.get("width", 0) < rule.get("min_width", 0):
        return False
    if rect.get("height", 0) < rule.get("min_height", 0):
        return False
    href = element.get("href")
    if rule.get("href_path_prefix") or rule.get("required_query_keys"):
        if not href:
            return False
        parsed = urlparse(href)
        if rule.get("href_path_prefix") and not parsed.path.startswith(
            rule["href_path_prefix"]
        ):
            return False
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(not query.get(key) for key in rule.get("required_query_keys", [])):
            return False
    return True


def find_all(snapshot: dict, rule: dict) -> list[dict]:
    return [element for element in snapshot.get("elements", []) if matches(element, rule)]


def find_first(snapshot: dict, rule: dict) -> dict | None:
    return next(iter(find_all(snapshot, rule)), None)


def find_open_detail(page: dict, config: dict) -> dict | None:
    """Return the element proving a note detail is on screen, if any.

    Xiaohongshu renders a note either as an overlay over the results page or as
    a standalone page depending on window width, and the two layouts do not
    share a container class. `detail.open_markers` lists the alternatives.
    """
    names = config["detail"].get("open_markers") or ["container"]
    for name in names:
        rule = config["detail"].get(name)
        if rule and (found := find_first(page, rule)):
            return found
    return None


def should_stop_scroll(
    stop_when: list[str], step: dict, previous_step: dict | None
) -> str | None:
    """Decide whether a scroll loop should stop.

    Returns the name of the rule that fired, or None to keep scrolling. The
    rules live in `locators.yaml` so a page that stops behaving differently can
    be handled by editing configuration rather than the script.
    """
    conditions = set(stop_when or [])

    if "moved_false" in conditions and not step.get("moved"):
        return "moved_false"

    if previous_step is not None:
        same_position = step.get("scrollY") == previous_step.get("scrollY") and step.get(
            "maxScrollY"
        ) == previous_step.get("maxScrollY")
        if "no_progress" in conditions and same_position:
            return "no_progress"

    if "at_max" in conditions:
        maximum = step.get("maxScrollY")
        if maximum is not None and step.get("scrollY", 0) >= maximum:
            return "at_max"

    return None


def contains_rect(container: dict, child: dict) -> bool:
    outer, inner = container.get("rect") or {}, child.get("rect") or {}
    return (
        outer.get("x", 0) <= inner.get("x", 0)
        and outer.get("y", 0) <= inner.get("y", 0)
        and outer.get("x", 0) + outer.get("width", 0)
        >= inner.get("x", 0) + inner.get("width", 0)
        and outer.get("y", 0) + outer.get("height", 0)
        >= inner.get("y", 0) + inner.get("height", 0)
    )
