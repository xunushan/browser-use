"""Test extension manifest and resource validation."""

import json
import pathlib

from chrome_agent.utils.extension_id import extension_id, manifest_extension_id


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


def test_manifest_pins_the_extension_id():
    """A loaded-by-hand extension keeps one ID, so the installer can know it.

    Without this key Chrome derives the ID from the directory the extension was
    loaded from, which is exactly what made the installer ask the user to copy
    an ID out of chrome://extensions.
    """
    ext_dir = pathlib.Path(__file__).parent.parent / "extension"

    with open(ext_dir / "manifest.json") as f:
        manifest = json.load(f)

    assert manifest.get("key"), "manifest.json should carry the pinned public key"
    identifier = manifest_extension_id(ext_dir / "manifest.json")
    assert identifier is not None
    assert len(identifier) == 32
    assert set(identifier) <= set("abcdefghijklmnop")
    # Without the key Chrome would derive the ID from the directory the
    # extension was loaded from; a pinned ID must not look like one.
    assert identifier != "ljddnkahpmiaklkfhimhandipjhpknmj"


def test_the_id_follows_chromium():
    """SHA256 of the key, first 16 bytes as hex, then 0-f shifted to a-p.

    The expectations were computed separately (openssl for the digest, an
    explicit translation table for the alphabet), and the rule as a whole was
    checked against a real ID: hashing the path of an unpacked extension
    reproduces the ID Chrome shows for it.
    """
    assert extension_id("aGVsbG8=") == "cmpcenlkfplakdaocgoidlckmfljocjo"
    assert extension_id("Y2hyb21lLWFnZW50") == "jmimmbkgeldngcanlcobhighhmmiligb"


def test_unpadded_and_wrapped_keys_decode_alike():
    assert extension_id("aGVsbG8") == extension_id("aGVs bG8=\n")


def test_a_manifest_without_a_key_pins_nothing(tmp_path):
    keyless = tmp_path / "manifest.json"
    keyless.write_text('{"manifest_version": 3}', encoding="utf-8")

    assert manifest_extension_id(keyless) is None
