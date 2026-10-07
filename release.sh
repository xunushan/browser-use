#!/usr/bin/env bash
# Build the release artifacts from a checkout.
#
# Three things get distributed, because they are installed three different ways:
# the wheel is a Python runtime, the extension zip is loaded by hand at
# chrome://extensions, and the skill tarball is read by an agent. The bundle
# carries all three plus install.sh, and is what a user unpacks to install
# without keeping the repository around.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

DIST="dist"
VERSION="$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)"
BUNDLE="chrome-agent-$VERSION"

rm -rf "$DIST"
mkdir -p "$DIST/stage/$BUNDLE"

python3 -m pip wheel --quiet --no-deps --wheel-dir "$DIST" .
WHEEL="$(ls -t "$DIST"/chrome_agent-*.whl | head -1)"

(cd extension && zip -qr "$OLDPWD/$DIST/chrome-agent-extension-$VERSION.zip" . -x '*.DS_Store')
tar -czf "$DIST/chrome-agent-skill-$VERSION.tar.gz" \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
  -C skill chrome-agent

cp install.sh README.md LICENSE "$WHEEL" "$DIST/stage/$BUNDLE/"
cp -R extension skill "$DIST/stage/$BUNDLE/"
# Bytecode caches are a local artifact of running the scripts; they must not
# ride along into a release.
find "$DIST/stage/$BUNDLE" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$DIST/stage/$BUNDLE" -name '.DS_Store' -delete
tar -czf "$DIST/$BUNDLE-bundle.tar.gz" -C "$DIST/stage" "$BUNDLE"

(cd "$DIST" && shasum -a 256 chrome_agent-*.whl chrome-agent-*.zip chrome-agent-*.tar.gz >SHA256SUMS)
rm -rf "$DIST/stage"

echo "Chrome Agent $VERSION built into $DIST:"
ls -1 "$DIST"
