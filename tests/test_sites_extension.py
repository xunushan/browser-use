"""Reading and dropping site access, which only the extension can do.

Chrome's permission store is the single record of which sites the extension may
touch. Nothing outside the browser can read it, so `sites list` and `sites
revoke` are forwards like any other command, and the whole implementation lives
in background.js. These are source-level checks for the parts that cannot be
observed from outside Chrome: that the broad patterns the tool declares for
itself are never reported as sites, that expected failures come back as results
rather than protocol errors, and that none of this quietly acquired a permission.
"""

import json
import pathlib
import re

EXTENSION_DIR = pathlib.Path(__file__).parent.parent / "extension"
BACKGROUND = (EXTENSION_DIR / "background.js").read_text(encoding="utf-8")

# The tool's own capability, not a site anybody chose.
DECLARED_PATTERNS = ("http://*/*", "https://*/*")


def handler_body() -> str:
    """The command handler's body, where the two cases have to be."""
    start = BACKGROUND.index("function handleDaemonCommand")
    return BACKGROUND[start : BACKGROUND.index("\n}\n", start)]


def sites_source() -> str:
    """Just the site-authorization section, so nothing else can satisfy a check."""
    start = BACKGROUND.index("// Site authorization.")
    return BACKGROUND[start : BACKGROUND.index("// Content Script injection functions", start)]


class TestTheCommandsAreWired:
    def test_the_handler_knows_both_commands(self):
        body = handler_body()

        assert re.search(r'case\s+"sites\.list"\s*:', body)
        assert re.search(r'case\s+"sites\.revoke"\s*:', body)

    def test_list_reads_chromes_permission_store(self):
        assert "chrome.permissions.getAll()" in sites_source()

    def test_revoke_uses_removal_not_a_local_notebook(self):
        """Removal is a Chrome call; a list kept here would be a second truth."""
        assert "chrome.permissions.remove(" in sites_source()


class TestWhatCountsAsASite:
    def test_the_declared_patterns_are_never_reported_as_sites(self):
        """`http://*/*` is the ability to ask, not a site the user picked.

        Chrome normally reports only the origin the popup requested, so this is
        an invariant held rather than a bug fixed: if the broad pattern ever did
        come back, "the sites you authorized" would list the whole web.
        """
        source = sites_source()

        for pattern in DECLARED_PATTERNS:
            assert pattern in source, pattern
        assert "TOOL_HOST_PATTERNS.has(origin)" in source

    def test_only_http_sites_are_listed(self):
        assert re.search(r"\^https\?:\\/\\/", sites_source())


class TestExpectedFailuresAreResultsNotProtocolErrors:
    def test_the_sites_functions_never_raise_a_protocol_error(self):
        """A JSON-RPC error gets wrapped by the daemon in its own wording.

        "Failed to forward to extension: not an http(s) site" buries the one
        part the caller needs, so bad input and a refused removal come back as
        ordinary results carrying an `error` key.
        """
        assert "sendError" not in sites_source()

    def test_a_site_that_was_never_granted_is_not_an_error(self):
        """Revoking twice ends in the same state, so the second is not a failure."""
        source = sites_source()

        assert "chrome.permissions.contains(" in source
        assert re.search(r"if\s*\(!granted\)\s*\{", source)

    def test_the_chrome_error_is_passed_through_verbatim(self):
        """If removal turns out to need a gesture, that message must survive."""
        source = sites_source()

        assert re.search(r"Could not revoke \$\{pattern\}: \$\{error\.message\}", source)


class TestNoPermissionWasAcquired:
    def test_the_sites_feature_needs_no_new_permission(self):
        manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

        assert set(manifest["permissions"]) == {
            "scripting",
            "storage",
            "tabs",
            "activeTab",
            "nativeMessaging",
            "alarms",
            "downloads",
        }

    def test_no_site_is_authorized_at_install_time(self):
        manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

        assert "host_permissions" not in manifest
        assert set(manifest["optional_host_permissions"]) == set(DECLARED_PATTERNS)


class TestGrantingStaysInThePopup:
    def test_nothing_here_asks_for_a_permission(self):
        """request() needs a user gesture, which no command has."""
        assert "chrome.permissions.request(" not in sites_source()
