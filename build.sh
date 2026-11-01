#!/usr/bin/env bash
# Build a single-file, dependency-free executable: dist/termwrapped.pyz
# Anyone with Python 3.9+ can run it:  python3 termwrapped.pyz
set -euo pipefail
cd "$(dirname "$0")"

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p dist
cp -r termwrapped "$stage/"
find "$stage" -name '__pycache__' -prune -exec rm -rf {} +
python3 -m zipapp "$stage" -o dist/termwrapped.pyz -m "termwrapped.cli:main" -p "/usr/bin/env python3" -c
echo "built dist/termwrapped.pyz ($(du -h dist/termwrapped.pyz | cut -f1))"
