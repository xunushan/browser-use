"""The extension reloading itself, which is what makes an update take effect.

Chrome applies changed files to an unpacked extension only when the extension is
reloaded. The button for that lives in chrome://extensions, but the extension can
also reload itself, with no permission and no click. These are source-level
checks: the ordering they cover cannot be observed from outside the browser, and
getting it wrong is silent — the daemon waits out its whole timeout.
"""

import json
import pathlib
import re

EXTENSION_DIR = pathlib.Path(__file__).parent.parent / "extension"
BACKGROUND = (EXTENSION_DIR / "background.js").read_text(encoding="utf-8")


def handler_body() -> str:
    """The command handler's body, where the ordering has to be right."""
    start = BACKGROUND.index("function handleDaemonCommand")
    return BACKGROUND[start : BACKGROUND.index("\n}\n", start)]


class TestReloadCommand:
    def test_the_handler_knows_the_reload_command(self):
        body = handler_body()

        assert re.search(r'case\s+"extension\.reload"\s*:', body)

    def test_the_reload_is_deferred_past_the_response(self):
        """chrome.runtime.reload() kills this worker, so it cannot run inline.

        An inline reload takes the port down with it and the response to the
        request that asked for the reload is never sent.
        """
        body = handler_body()

        assert "setTimeout" in body
        assert "chrome.runtime.reload()" in body
        # Deferred, not merely mentioned: the call sits inside a timer.
        timer = re.search(r"setTimeout\(([^;]*?)\);", body, re.DOTALL)
        assert timer is not None
        assert "chrome.runtime.reload()" in timer.group(1)

    def test_the_response_is_sent_before_the_timer_is_set(self):
        """Order in the source is the whole mechanism."""
        body = handler_body()

        assert body.index("sendResponse(id, result)") < body.index("setTimeout")

    def test_the_reload_waits_long_enough_for_the_response_to_leave(self):
        body = handler_body()

        delay = int(re.search(r"setTimeout\([^,]*,\s*(\d+)\)", body).group(1))

        assert 0 < delay <= 1000

    def test_the_reload_needs_no_permission(self):
        """The manifest is where a permission would have to appear."""
        manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

        assert "runtime" not in manifest.get("permissions", [])
        assert "management" not in manifest.get("permissions", [])
