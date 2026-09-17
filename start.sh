#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11+；可设置 PYTHON=python3.11"'
if [ ! -d .venv ]; then "$PYTHON" -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.db
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
