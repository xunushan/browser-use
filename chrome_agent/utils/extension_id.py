"""The extension ID that a manifest's `key` pins.

Chrome derives an extension ID from its public key: SHA256 of the key, its first
16 bytes as hex, then every hex digit shifted into the `a`-`p` alphabet. Both
halves are in Chromium's `components/crx_file/id_util.cc` — `kIdSize = 16`
("First 16 bytes of SHA256 hashed public key") and `ConvertHexadecimalToIDAlphabet`,
whose comment says the shift exists "to avoid ever having a completely numeric
host, since some software interprets that as an IP address" — and doing the same
in Python was checked against a real ID: hashing the path of an unpacked
extension reproduces the ID Chrome shows for it.

With that key in `extension/manifest.json`, an unpacked extension keeps one ID
across machines (https://developer.chrome.com/docs/extensions/reference/manifest/key:
"This value maintains the unique ID of an extension ... when it is loaded during
development"), which is what lets the installer write the Native Messaging host
manifest itself instead of asking the user to copy an ID out of chrome://extensions.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path

ID_HEX_DIGITS = 32
_ALPHABET_START = ord("a")


def extension_id(public_key: str) -> str:
    """The 32-character extension ID pinned by a base64 manifest `key`."""
    encoded = "".join(public_key.split())
    padding = "=" * (-len(encoded) % 4)
    try:
        key_bytes = base64.b64decode(encoded + padding, validate=True)
    except binascii.Error as error:
        raise ValueError(f"manifest key is not valid base64: {error}") from error
    digest = hashlib.sha256(key_bytes).hexdigest()[:ID_HEX_DIGITS]
    return "".join(chr(_ALPHABET_START + int(digit, 16)) for digit in digest)


def manifest_extension_id(manifest_path: Path) -> str | None:
    """The ID a manifest pins, or None when it carries no `key`."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = manifest.get("key")
    if not isinstance(key, str) or not key:
        return None
    return extension_id(key)
