#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/dist"
git -C "$ROOT" archive --format=zip --prefix=threadforge/ -o "$ROOT/dist/threadforge-drop2.zip" HEAD
echo "Wrote $ROOT/dist/threadforge-drop2.zip"

