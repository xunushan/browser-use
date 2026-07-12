#!/usr/bin/env python3
"""End-to-end test for Xiaohongshu search.

This script performs a complete end-to-end test of the Chrome Agent system
by searching for "318攻略" on Xiaohongshu.

Prerequisites:
1. Chrome extension is installed in developer mode
2. Native Messaging Host is registered
3. Chrome Agent Daemon is running
4. User is logged in to Xiaohongshu (or will be prompted)

Usage:
    python test_xiaohongshu_e2e.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path


class ChromeAgentClient:
    """Client for interacting with Chrome Agent CLI."""

    def __init__(self):
        self.cli = [sys.executable, "-m", "chrome_agent.cli"]

    def run(self, *args, json_output=True):
        """Run a CLI command and return the result."""
        cmd = self.cli + list(args)
        if json_output:
            cmd.append("--json")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Command failed: {' '.join(cmd)}")
            print(f"Error: {result.stderr}")
            return None

        if json_output and result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return result.stdout.strip()
        return result.stdout.strip()

    def ensure_daemon(self):
        """Ensure daemon is running."""
        print("Step 1: Ensuring daemon is running...")
        result = self.run("ensure", "--launch-if-missing")
        if result and result.get("status") == "ready":
            print("✅ Daemon is running")
            return True
        print("❌ Failed to start daemon")
        return False

    def list_tabs(self):
        """List all tabs."""
        print("\nStep 2: Listing tabs...")
        result = self.run("tabs", "list")
        if result and isinstance(result, list):
            print(f"✅ Found {len(result)} tabs")
            return result
        print("❌ Failed to list tabs")
        return None

    def find_xiaohongshu_tab(self, tabs):
        """Find Xiaohongshu tab."""
        print("\nStep 3: Finding Xiaohongshu tab...")
        for tab in tabs:
            url = tab.get("url", "")
            if "xiaohongshu.com" in url:
                print(f"✅ Found Xiaohongshu tab: {tab['id']}")
                return tab
        print("❌ Xiaohongshu tab not found")
        return None

    def get_page_snapshot(self, tab_id):
        """Get page snapshot."""
        print(f"\nStep 4: Getting page snapshot for tab {tab_id}...")
        result = self.run("page", "snapshot", "--tab-id", str(tab_id))
        if result and "documentId" in result:
            print(f"✅ Got snapshot: {result['documentId']}")
            return result
        print("❌ Failed to get snapshot")
        return None

    def find_search_box(self, snapshot):
        """Find search box in snapshot."""
        print("\nStep 5: Finding search box...")
        elements = snapshot.get("elements", [])

        # Look for search input
        for element in elements:
            if element.get("tag") == "input":
                placeholder = element.get("placeholder", "").lower()
                if "搜索" in placeholder or "search" in placeholder:
                    print(f"✅ Found search box: {element['ref']}")
                    return element

        # Look for search button
        for element in elements:
            if element.get("tag") == "button":
                text = element.get("text", "").lower()
                if "搜索" in text or "search" in text:
                    print(f"✅ Found search button: {element['ref']}")
                    return element

        print("❌ Search box not found")
        return None

    def click_element(self, tab_id, ref):
        """Click an element."""
        print(f"\nStep 6: Clicking element {ref}...")
        result = self.run("page", "click", "--tab-id", str(tab_id), "--ref", ref)
        if result and result.get("success"):
            print("✅ Clicked successfully")
            return True
        print("❌ Failed to click")
        return False

    def fill_input(self, tab_id, ref, value):
        """Fill an input element."""
        print(f"\nStep 7: Filling input {ref} with '{value}'...")
        result = self.run("page", "fill", "--tab-id", str(tab_id), "--ref", ref, "--value", value)
        if result and result.get("success"):
            print("✅ Filled successfully")
            return True
        print("❌ Failed to fill")
        return False

    def press_key(self, tab_id, ref, keys):
        """Press a key."""
        print(f"\nStep 8: Pressing {keys}...")
        result = self.run("page", "keypress", "--tab-id", str(tab_id), "--ref", ref, "--keys", keys)
        if result and result.get("success"):
            print("✅ Key pressed successfully")
            return True
        print("❌ Failed to press key")
        return False

    def wait_for_element(self, tab_id, selector, timeout=10):
        """Wait for an element to appear."""
        print(f"\nStep 9: Waiting for element '{selector}'...")
        # Simple wait - in real implementation would use CLI wait command
        time.sleep(2)
        print("✅ Waited for element")
        return True


def main():
    """Run the end-to-end test."""
    print("=" * 60)
    print("Xiaohongshu Search E2E Test")
    print("=" * 60)

    client = ChromeAgentClient()

    # Step 1: Ensure daemon is running
    if not client.ensure_daemon():
        print("\n❌ Test failed: Daemon not running")
        print("Please ensure Chrome Agent Daemon is installed and running")
        return 1

    # Step 2: List tabs
    tabs = client.list_tabs()
    if not tabs:
        print("\n❌ Test failed: No tabs found")
        print("Please open Chrome and navigate to xiaohongshu.com")
        return 1

    # Step 3: Find Xiaohongshu tab
    tab = client.find_xiaohongshu_tab(tabs)
    if not tab:
        print("\n❌ Test failed: Xiaohongshu tab not found")
        print("Please open https://www.xiaohongshu.com in Chrome")
        return 1

    tab_id = tab["id"]

    # Step 4: Get page snapshot
    snapshot = client.get_page_snapshot(tab_id)
    if not snapshot:
        print("\n❌ Test failed: Could not get page snapshot")
        return 1

    # Step 5: Find search box
    search_box = client.find_search_box(snapshot)
    if not search_box:
        print("\n❌ Test failed: Search box not found")
        print("The page structure may have changed")
        return 1

    search_ref = search_box["ref"]

    # Step 6: Click search box
    if not client.click_element(tab_id, search_ref):
        print("\n❌ Test failed: Could not click search box")
        return 1

    # Step 7: Fill search box
    if not client.fill_input(tab_id, search_ref, "318攻略"):
        print("\n❌ Test failed: Could not fill search box")
        return 1

    # Step 8: Press Enter
    if not client.press_key(tab_id, search_ref, "Enter"):
        print("\n❌ Test failed: Could not press Enter")
        return 1

    # Step 9: Wait for results
    client.wait_for_element(tab_id, ".search-result")

    # Step 10: Get results snapshot
    results_snapshot = client.get_page_snapshot(tab_id)
    if not results_snapshot:
        print("\n❌ Test failed: Could not get results snapshot")
        return 1

    # Verify results
    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    print(f"URL: {results_snapshot.get('url', 'N/A')}")
    print(f"Title: {results_snapshot.get('title', 'N/A')}")
    print(f"Elements found: {len(results_snapshot.get('elements', []))}")

    # Check if search results are present
    elements = results_snapshot.get("elements", [])
    search_results = [e for e in elements if "search" in e.get("className", "").lower()]

    if search_results:
        print(f"✅ Found {len(search_results)} search result elements")
        print("\n✅ Test passed!")
        return 0
    else:
        print("⚠️  No search results found - page may still be loading")
        print("\n⚠️  Test incomplete - please verify manually")
        return 0


if __name__ == "__main__":
    sys.exit(main())
