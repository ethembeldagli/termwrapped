#!/bin/sh
# Build a single-file, dependency-free executable: dist/termwrapped.pyz
# Anyone with Python 3.9+ can run it:  python3 termwrapped.pyz
# Plain POSIX sh + Python only, so it builds on minimal images too.
set -eu
cd "$(dirname "$0")"
python3 - <<'EOF'
import os
import shutil
import tempfile
import zipapp

with tempfile.TemporaryDirectory() as stage:
    shutil.copytree("termwrapped", os.path.join(stage, "termwrapped"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.makedirs("dist", exist_ok=True)
    zipapp.create_archive(stage, "dist/termwrapped.pyz", interpreter="/usr/bin/env python3",
                          main="termwrapped.cli:main", compressed=True)
print(f"built dist/termwrapped.pyz ({os.path.getsize('dist/termwrapped.pyz') // 1024} KB)")
EOF
