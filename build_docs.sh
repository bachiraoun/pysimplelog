#!/usr/bin/env bash
# Build pysimplelog's Sphinx documentation and open it in the default browser.
#
# Wraps the existing docs/Makefile (which already points SPHINXBUILD at
# .sphinx-venv/bin/sphinx-build) so there's one command to remember instead
# of juggling venvs and paths by hand:
#
#     ./build_docs.sh
#
# Cross-platform open: `open` on macOS, `xdg-open` on Linux, `start` on
# Windows (Git Bash/MSYS).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_DIR="$REPO_ROOT/docs"
INDEX_HTML="$DOCS_DIR/build/html/index.html"

if [ ! -x "$REPO_ROOT/.sphinx-venv/bin/sphinx-build" ]; then
    echo "error: .sphinx-venv/bin/sphinx-build not found -- set up the docs venv first:" >&2
    echo "  python3 -m venv .sphinx-venv && .sphinx-venv/bin/pip install sphinx" >&2
    exit 1
fi

echo "Building docs..."
make -C "$DOCS_DIR" clean html

echo "Opening $INDEX_HTML ..."
case "$(uname -s)" in
    Darwin)  open "$INDEX_HTML" ;;
    Linux)   xdg-open "$INDEX_HTML" >/dev/null 2>&1 & ;;
    MINGW*|MSYS*|CYGWIN*) start "" "$INDEX_HTML" ;;
    *) echo "Don't know how to auto-open a browser on this OS -- open manually: $INDEX_HTML" ;;
esac
