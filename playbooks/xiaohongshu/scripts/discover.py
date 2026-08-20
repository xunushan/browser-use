#!/usr/bin/env python3
"""Discover Xiaohongshu result links from a Chrome Agent snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from urllib.parse import urlparse


def chrome_agent(*args: str) -> dict:
    result = subprocess.run(
        ["chrome-agent", *args, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def discover(snapshot: dict, limit: int) -> list[dict]:
    results = []
    seen = set()
    for element in snapshot.get("elements", []):
        href = element.get("href")
        if not href or href in seen:
            continue
        parsed = urlparse(href)
        if not parsed.hostname or not parsed.hostname.endswith("xiaohongshu.com"):
            continue
        if not parsed.path.startswith("/explore/"):
            continue
        seen.add(href)
        results.append(
            {
                "rank": len(results) + 1,
                "ref": element.get("ref"),
                "title": (element.get("text") or "").strip() or None,
                "href": href,
                "hasAccessContext": "xsec_token=" in parsed.query,
            }
        )
        if len(results) >= limit:
            break
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tab-id", required=True, type=int)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    snapshot = chrome_agent(
        "page",
        "snapshot",
        "--tab-id",
        str(args.tab_id),
        "--scope",
        "full",
    )
    output = {
        "source": {"tabId": args.tab_id, "url": snapshot.get("url")},
        "results": discover(snapshot, max(1, args.limit)),
        "truncatedSnapshot": bool(snapshot.get("truncated")),
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

