"""Test extension manifest and resource validation."""

import json
import pathlib


def test_extension_structure():
    """Verify extension directory has all required files."""
    ext_dir = pathlib.Path(__file__).parent.parent / "extension"

    # Required files
    required_files = [
        "manifest.json",
        "background.js",
        "content.js",
        "popup.html",
        "popup.js",
    ]
    for file in required_files:
        assert (ext_dir / file).exists(), f"Missing required file: {file}"


def test_manifest_valid():
    """Verify manifest.json is valid and references existing files."""
    ext_dir = pathlib.Path(__file__).parent.parent / "extension"
    manifest_path = ext_dir / "manifest.json"

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Check required fields
    assert manifest["manifest_version"] == 3
    assert manifest["name"] == "Chrome Agent"
    assert "permissions" in manifest
    assert "nativeMessaging" in manifest["permissions"]
    assert "activeTab" in manifest["permissions"]
    assert "downloads" in manifest["permissions"]

    # Check background script exists
    bg_script = manifest["background"]["service_worker"]
    assert (ext_dir / bg_script).exists(), f"Background script missing: {bg_script}"

    # Check icons exist (or are placeholders)
    for _size, path in manifest.get("icons", {}).items():
        icon_path = ext_dir / path
        assert icon_path.exists(), f"Icon missing: {path}"
