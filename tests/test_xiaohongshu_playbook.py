"""Regression tests for configuration-driven Xiaohongshu Playbook rules."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "playbooks" / "xiaohongshu" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discover  # noqa: E402
from discover import close_detail_if_open, open_result  # noqa: E402
from runtime import load_locators, note_id, should_stop_scroll  # noqa: E402

NOTE = "6ac48ca100000000140034ed"
OTHER = "6ac4c9f80000000015017110"
NOTE_URL = f"https://www.xiaohongshu.com/explore/{NOTE}?xsec_token=token&xsec_source=pc_search"
OTHER_URL = f"https://www.xiaohongshu.com/explore/{OTHER}?xsec_token=token"
SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword=%25E4%25B9%259D%25E5%25AF%25A8"


def element(ref: str, **kwargs: object) -> dict:
    result = {
        "ref": ref,
        "tag": "a",
        "className": "",
        "href": None,
        "text": None,
        "states": {"visible": True},
        "rect": {"x": 0, "y": 0, "width": 100, "height": 100},
    }
    result.update(kwargs)
    return result


def page(url: str, *elements: dict) -> dict:
    return {"url": url, "elements": list(elements)}


def search_page() -> dict:
    return page(SEARCH_URL, element("search", tag="input", className="search-input"))


def detail_page(url: str = NOTE_URL, *, with_close: bool = True, with_mask: bool = True) -> dict:
    elements = [
        element("container", className="note-container", rect={"x": 0, "y": 0, "width": 600, "height": 740}),
        element("body", className="note-text"),
    ]
    if with_close:
        elements.append(element("close", tag="button", className="reds-button-new close-icon"))
    if with_mask:
        elements.append(element("mask", className="note-detail-mask"))
    return page(url, *elements)


class FakeBrowser:
    """Serve queued snapshots in order; the last one repeats."""

    def __init__(self, *pages: dict) -> None:
        self._queue = list(pages)
        self.calls: list[tuple] = []

    def __call__(self, *args: str) -> dict:
        self.calls.append(args)
        if args[:2] == ("page", "snapshot"):
            return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
        return {"success": True, "clicked": True, "keypressed": args[-1]}

    def modes(self) -> list[str]:
        return [args[0] + "." + args[1] for args in self.calls if args[:2] != ("page", "snapshot")]


@pytest.fixture
def config() -> dict:
    return load_locators()


# --- search discovery -------------------------------------------------------


def test_search_discovery_keeps_visible_signed_result_cards_and_title(config) -> None:
    href = f"https://www.xiaohongshu.com/search_result/{NOTE}?xsec_token=token&xsec_source=pc_search"
    found = discover.discover(
        page(
            SEARCH_URL,
            element(
                "bad",
                href=f"https://www.xiaohongshu.com/explore/{NOTE}",
                className="overlay",
                states={"visible": False},
                rect={"x": 0, "y": 0, "width": 0, "height": 0},
            ),
            element("card", tag="section", className="note-item", text="卡片回退标题"),
            element("cover", href=href, className="cover mask ld"),
            element("title", href=href, className="title", text="准确标题"),
        ),
        config,
        limit=10,
    )

    assert found == [
        {
            "rank": 1,
            "ref": "cover",
            "title": "准确标题",
            "href": href,
            "noteId": NOTE,
            "hasAccessContext": True,
        }
    ]


def test_search_discovery_falls_back_to_enclosing_card_text(config) -> None:
    href = f"https://www.xiaohongshu.com/search_result/{NOTE}?xsec_token=token"
    found = discover.discover(
        page(
            SEARCH_URL,
            element(
                "card",
                tag="section",
                className="note-item",
                text="卡片回退标题",
                rect={"x": 0, "y": 0, "width": 200, "height": 300},
            ),
            element(
                "cover",
                href=href,
                className="cover mask ld",
                rect={"x": 10, "y": 10, "width": 150, "height": 200},
            ),
        ),
        config,
        limit=1,
    )

    assert found[0]["title"] == "卡片回退标题"


# --- helpers -----------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        NOTE_URL,
        f"https://www.xiaohongshu.com/search_result/{NOTE}?xsec_token=token",
        f"https://www.xiaohongshu.com/discovery/item/{NOTE}",
    ],
)
def test_note_id_reads_every_url_shape(url) -> None:
    assert note_id(url) == NOTE


@pytest.mark.parametrize(
    ("url", "expected"),
    [(None, None), (SEARCH_URL, None), ("https://www.xiaohongshu.com/explore", None)],
)
def test_note_id_ignores_non_note_urls(url, expected) -> None:
    assert note_id(url) is expected


def test_should_stop_scroll_reports_the_rule_that_fired() -> None:
    rules = ["moved_false", "no_progress"]
    assert should_stop_scroll(rules, {"moved": False}, None) == "moved_false"
    assert should_stop_scroll(rules, {"moved": True, "scrollY": 900}, None) is None
    # Position frozen between two steps means lazy loading has run out.
    assert (
        should_stop_scroll(rules, {"moved": True, "scrollY": 900}, {"scrollY": 900})
        == "no_progress"
    )
    assert (
        should_stop_scroll(rules, {"moved": True, "scrollY": 1800}, {"scrollY": 900}) is None
    )


# --- closing an open detail -------------------------------------------------


def test_close_detail_is_a_noop_when_no_detail_is_open(monkeypatch, config) -> None:
    fake = FakeBrowser(search_page())
    monkeypatch.setattr(discover, "chrome_agent", fake)

    assert close_detail_if_open(1, config) is None
    assert fake.calls == [("page", "snapshot", "--tab-id", "1", "--scope", "full")]


def test_close_detail_clicks_the_close_control(monkeypatch, config) -> None:
    fake = FakeBrowser(detail_page(), search_page())
    monkeypatch.setattr(discover, "chrome_agent", fake)

    assert close_detail_if_open(1, config) == "close_control"
    assert fake.modes() == ["page.click"]


def test_close_detail_falls_back_to_keypress_when_control_is_hidden(monkeypatch, config) -> None:
    """The narrow layout hides the close button; Escape is what dismisses it."""
    fake = FakeBrowser(detail_page(with_close=False), detail_page(with_close=False), search_page())
    monkeypatch.setattr(discover, "chrome_agent", fake)

    assert close_detail_if_open(1, config) == "keypress:Escape"
    assert fake.modes() == ["page.keypress"]


def test_close_detail_handles_a_layout_without_note_container(monkeypatch, config) -> None:
    """Wide windows render the note as a standalone page: mask, no container."""
    standalone = page(NOTE_URL, element("mask", className="note-detail-mask"))
    fake = FakeBrowser(standalone, standalone, search_page())
    monkeypatch.setattr(discover, "chrome_agent", fake)

    assert close_detail_if_open(1, config) == "keypress:Escape"


def test_close_detail_raises_when_nothing_dismisses_it(monkeypatch, config) -> None:
    fake = FakeBrowser(detail_page(with_close=False))
    monkeypatch.setattr(discover, "chrome_agent", fake)
    monkeypatch.setattr(discover, "DETAIL_CLOSE_TIMEOUT", 0.0)

    with pytest.raises(RuntimeError, match="详情遮罩仍开着"):
        close_detail_if_open(1, config)


# --- opening a result -------------------------------------------------------


def selected(rank: int = 1, ref: str = "cover", target: str = NOTE) -> dict:
    return {
        "rank": rank,
        "ref": ref,
        "noteId": target,
        "title": "t",
        "href": f"https://www.xiaohongshu.com/search_result/{target}?xsec_token=token",
    }


def test_open_result_confirms_the_landing_note(monkeypatch, config) -> None:
    fake = FakeBrowser(detail_page())
    monkeypatch.setattr(discover, "chrome_agent", fake)

    opened = open_result(1, selected(), "click", config)

    assert opened["noteId"] == NOTE
    assert opened["mode"] == "click"
    assert fake.modes() == ["page.click"]


def test_open_result_falls_back_to_navigate_when_the_click_mislands(monkeypatch, config) -> None:
    """A click that hits the overlay reports success but stays on the old note."""
    fake = FakeBrowser(detail_page(OTHER_URL), detail_page(NOTE_URL))
    monkeypatch.setattr(discover, "chrome_agent", fake)
    monkeypatch.setattr(discover, "NOTE_OPEN_TIMEOUT", 0.0)

    opened = open_result(1, selected(), "click", config)

    assert opened["mode"] == "navigate"
    assert fake.modes() == ["page.click", "tabs.navigate"]


def test_open_result_raises_instead_of_collecting_the_wrong_note(monkeypatch, config) -> None:
    fake = FakeBrowser(detail_page(OTHER_URL))
    monkeypatch.setattr(discover, "chrome_agent", fake)
    monkeypatch.setattr(discover, "NOTE_OPEN_TIMEOUT", 0.0)

    with pytest.raises(RuntimeError, match="没有落在目标笔记"):
        open_result(1, selected(), "click", config)
