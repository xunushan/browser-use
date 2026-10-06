#!/usr/bin/env python3
"""Collect one open Xiaohongshu note using refs resolved by an agent."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from runtime import find_first, load_locators, should_stop_scroll


def chrome_agent(*args: str) -> dict:
    result = subprocess.run(
        ["chrome-agent", *args, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    payload = json.loads(result.stdout)
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload


def tab_source(tab_id: int) -> dict:
    tabs = chrome_agent("tabs", "list").get("tabs", [])
    tab = next((item for item in tabs if item.get("id") == tab_id), None)
    if not tab:
        raise RuntimeError(f"Tab not found: {tab_id}")
    return {"tabId": tab_id, "url": tab.get("url", ""), "title": tab.get("title")}


def deduplicate(items: list[dict], key: str = "url") -> list[dict]:
    output = []
    seen = set()
    for item in items:
        value = item.get(key)
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(item)
    return output


def extract_text(tab_id: int, ref: str | None, max_chars: int) -> dict:
    if not ref:
        return {"text": "", "length": 0, "truncated": False}
    result = chrome_agent(
        "page",
        "text",
        "--tab-id",
        str(tab_id),
        "--ref",
        ref,
        "--max-chars",
        str(max_chars),
    )
    return {
        "text": result.get("text", ""),
        "length": int(result.get("length", 0)),
        "truncated": bool(result.get("truncated")),
    }


def snapshot(tab_id: int) -> dict:
    return chrome_agent("page", "snapshot", "--tab-id", str(tab_id), "--scope", "full")


def load_comments(
    tab_id: int, config: dict, max_steps: int, fallback_ref: str | None
) -> tuple[str | None, list[str]]:
    """Scroll the configured note scroller until a configured rule says stop.

    The stop rules come from `locators.yaml`; see `runtime.should_stop_scroll`.
    Comments mount lazily, so the container is re-resolved after every step.
    """
    warnings: list[str] = []
    rules = config["detail"]
    scroll_config = config["scroll"]["comments"]
    stop_when = scroll_config.get("stop_when") or ["moved_false"]
    comments_ref: str | None = None
    stopped_by: str | None = None
    previous_step: dict | None = None
    steps = 0
    for steps in range(1, max_steps + 1):
        page = snapshot(tab_id)
        comments = find_first(page, rules["comments"])
        if comments:
            comments_ref = comments["ref"]
        target = find_first(page, rules["comments_scroll_target"])
        if not target:
            # Some layouts render the whole thread at once with no scroll
            # container. That is only a problem when nothing mounted yet.
            if not comments:
                warnings.append("未找到评论滚动容器，无法触发评论懒加载")
            stopped_by = "no_scroll_target"
            break
        step = chrome_agent(
            "page",
            "scroll",
            "--tab-id",
            str(tab_id),
            "--ref",
            target["ref"],
            "--dy",
            str(scroll_config["dy"]),
        )
        stopped_by = should_stop_scroll(stop_when, step, previous_step)
        if stopped_by:
            break
        previous_step = step
    final_comments = find_first(snapshot(tab_id), rules["comments"])
    if final_comments:
        comments_ref = final_comments["ref"]
    if not comments_ref:
        comments_ref = fallback_ref
    if stopped_by is None and max_steps:
        warnings.append(f"评论滚动达到上限 {steps} 步，当前评论可能不完整")
    if not comments_ref:
        warnings.append("评论容器未在滚动终止前出现")
    return comments_ref, warnings


def resolve_refs(
    page: dict, config: dict, fallbacks: dict[str, str | None]
) -> dict[str, str | None]:
    """Resolve several refs against one snapshot, keeping explicit fallbacks."""
    resolved = {}
    for name, fallback in fallbacks.items():
        element = find_first(page, config["detail"][name])
        resolved[name] = element["ref"] if element else fallback
    return resolved


def comment_items(text: str) -> list[dict]:
    """Convert the visible Xiaohongshu comment stream into comment records.

    `innerText` interleaves each comment with time/place, like counts and reply
    controls. A time line terminates the preceding author/body pair. The raw
    stream is retained separately because collapsed replies are not available.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    time_or_place = re.compile(
        r"^(?:\d+\s*(?:秒|分钟|分|小时|天)前|\d{4}-\d{2}-\d{2}|\d{2}-\d{2}).*$"
    )
    ui_text = re.compile(r"^(?:共\s*\d+\s*条评论|赞|回复|作者|展开\s*\d+\s*条回复|\d+)$")
    records: list[dict] = []
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        meaningful = [line for line in pending if not ui_text.fullmatch(line)]
        pending = []
        if len(meaningful) < 2:
            return
        records.append({
            "index": len(records) + 1,
            "author": meaningful[0],
            "text": "\n".join(meaningful[1:]),
        })

    for line in lines:
        if time_or_place.fullmatch(line):
            flush()
        elif not ui_text.fullmatch(line):
            pending.append(line)
    flush()
    return records


def is_note_image(image: dict) -> bool:
    """Exclude small UI assets/emoji while keeping Xiaohongshu note image variants."""
    url = image.get("src", "")
    width = image.get("width") or 0
    height = image.get("height") or 0
    if "notes_pre_post/" in url:
        return True
    if re.search(r"/1040g[0-9a-z]+", url, re.I) and max(width, height) > 300:
        return True
    return max(width, height) > 480


def unique_destination(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def organize_downloads(downloads: list[dict], directory: Path, warnings: list[str]) -> None:
    """Move only files confirmed as downloaded in this collection run."""
    directory.mkdir(parents=True, exist_ok=True)
    for item in downloads:
        if item.get("state") != "complete" or not item.get("filename"):
            continue
        source = Path(item["filename"])
        if not source.is_file():
            warnings.append(f"下载完成但找不到文件，未归档：{source}")
            continue
        destination = unique_destination(directory, source.name)
        shutil.move(str(source), destination)
        item["originalFilename"] = str(source)
        item["filename"] = str(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tab-id", required=True, type=int)
    parser.add_argument(
        "--body-ref", help="Optional fallback; normally resolved from locators.yaml"
    )
    parser.add_argument(
        "--comments-ref", help="Optional fallback; normally resolved from locators.yaml"
    )
    parser.add_argument(
        "--images-ref", help="Optional fallback; normally resolved from locators.yaml"
    )
    parser.add_argument(
        "--media-ref", help="Optional fallback; normally resolved from locators.yaml"
    )
    parser.add_argument(
        "--comment-scrolls", type=int, help="Override locators.yaml comment scroll limit"
    )
    parser.add_argument("--download-images", action="store_true")
    parser.add_argument("--download-media", action="store_true")
    parser.add_argument("--prefix", default="xiaohongshu-note")
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument(
        "--output", type=Path, help="JSON output path (legacy mode; media goes beside it)"
    )
    output_group.add_argument(
        "--output-dir", type=Path, help="Note directory; writes note.json plus images/ and videos/"
    )
    args = parser.parse_args()

    note_dir = args.output_dir or args.output.parent
    output_path = (args.output_dir / "note.json") if args.output_dir else args.output

    config = load_locators()
    configured_limit = config["scroll"]["comments"]["max_steps"]
    requested_limit = args.comment_scrolls
    comment_limit = max(0, requested_limit if requested_limit is not None else configured_limit)
    comments_ref, warnings = load_comments(
        args.tab_id, config, comment_limit, args.comments_ref
    )
    resolved = resolve_refs(
        snapshot(args.tab_id),
        config,
        {
            "body": args.body_ref,
            "image_media": args.images_ref,
            "video_media": args.media_ref,
        },
    )
    body_ref = resolved["body"]
    images_ref = resolved["image_media"]
    media_ref = resolved["video_media"]
    if not body_ref:
        raise RuntimeError("未从 locators.yaml 或 --body-ref 找到正文容器")

    content = extract_text(args.tab_id, body_ref, 20000)
    comments_text = extract_text(args.tab_id, comments_ref, 100000)
    if content["truncated"]:
        warnings.append("正文达到采集上限，可能不完整")
    if comments_ref:
        warnings.append("评论仅包含当前 Web 页面已加载和已展开的范围")

    images = []
    if images_ref:
        discovered_images = deduplicate(
            chrome_agent(
                "page",
                "images",
                "--tab-id",
                str(args.tab_id),
                "--ref",
                images_ref,
                "--load",
            ).get("images", [])
        )
        images = [image for image in discovered_images if is_note_image(image)]
        if discovered_images and not images:
            warnings.append("未识别出笔记原图，已拒绝下载小图/表情/页面资源")

    audio_video = []
    if media_ref:
        scoped_media = chrome_agent(
            "page", "media", "--tab-id", str(args.tab_id), "--ref", media_ref
        ).get("media", [])
        page_media = chrome_agent("page", "media", "--tab-id", str(args.tab_id)).get(
            "media", []
        )
        audio_video = deduplicate(scoped_media + page_media)

    downloads = []
    if args.download_images and images_ref:
        command = [
            "page", "download-images", "--tab-id", str(args.tab_id), "--ref", images_ref,
            "--prefix", args.prefix,
        ]
        for image in images:
            command.extend(["--url", image["src"]])
        result = chrome_agent(*command)
        image_downloads = result.get("downloads", [])
        organize_downloads(image_downloads, note_dir / "images", warnings)
        downloads.extend(image_downloads)
        if result.get("requested", 0) == 0:
            warnings.append("未下载图片：请重新确认图片容器是详情轮播，而非整张笔记或评论容器")
        if not images:
            images = [
                {"src": item["url"], "source": "download-discovery"}
                for item in result.get("downloads", [])
                if item.get("url")
            ]
    if args.download_media and media_ref:
        result = chrome_agent(
            "page",
            "download-media",
            "--tab-id",
            str(args.tab_id),
            "--prefix",
            args.prefix,
            "--timeout",
            "600",
        )
        media_downloads = result.get("downloads", [])
        organize_downloads(media_downloads, note_dir / "videos", warnings)
        downloads.extend(media_downloads)
        if result.get("unsupported"):
            warnings.append("存在当前无法直接下载的 blob/HLS/DASH/unsupported 媒体")

    output = {
        "schemaVersion": 1,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "source": tab_source(args.tab_id),
        "content": content,
        "comments": {
            "rawText": comments_text["text"],
            "items": comment_items(comments_text["text"]),
            "scope": "currently-loaded" if comments_ref else "none",
            "possiblyIncomplete": bool(comments_ref),
        },
        "media": {
            "images": images,
            "audioVideo": audio_video,
            "downloads": downloads,
        },
        "warnings": warnings,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
