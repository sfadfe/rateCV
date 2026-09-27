#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PY=""
for c in python3.12 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;sys.exit(sys.version_info[:2]!=(3,12))' 2>/dev/null; then
        PY="$c"; break
    fi
done
[ -n "$PY" ] || { echo "Python 3.12 not found. See README.md step 1."; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg not found. See README.md step 1."; exit 1; }

if [ ! -x .venv/bin/python ]; then
    echo "[1/3] creating venv..."
    "$PY" -m venv .venv
fi
echo "[2/3] installing packages (slow only the first time)..."
.venv/bin/python -m pip install -q -r requirements.txt
echo "[3/3] running"
.venv/bin/python run.py "$@"
