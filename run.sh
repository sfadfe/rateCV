#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PY=""
for c in python3.12 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;sys.exit(sys.version_info[:2]!=(3,12))' 2>/dev/null; then
        PY="$c"; break
    fi
done
[ -n "$PY" ] || { echo "Python 3.12 가 없다. README.md 1번 참고."; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg 가 없다. README.md 1번 참고."; exit 1; }

if [ ! -x .venv/bin/python ]; then
    echo "[1/3] 가상환경 만드는 중..."
    "$PY" -m venv .venv
fi
echo "[2/3] 패키지 설치 중 (처음 한 번만 오래 걸린다)..."
.venv/bin/python -m pip install -q -r requirements.txt
echo "[3/3] 실행"
.venv/bin/python run.py "$@"
