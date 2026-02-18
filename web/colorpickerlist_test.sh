#!/usr/bin/env bash
set -euo pipefail

# Basic tests for the embedded HSLuv implementation in colorpickerlist.html.
# Runs without external deps beyond Node.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML_FILE="$ROOT_DIR/colorpickerlist.html"

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is required" >&2
  exit 1
fi

if [[ ! -f "$HTML_FILE" ]]; then
  echo "ERROR: Missing $HTML_FILE" >&2
  exit 1
fi

node "$ROOT_DIR/colorpickerlist_test.js"
