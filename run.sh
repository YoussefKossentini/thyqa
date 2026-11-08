#!/usr/bin/env bash
# Thiqa: setup + start on Linux/macOS
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python -m pip install -q -r requirements-ml.txt || echo "[info] ML fraud signal disabled"
.venv/bin/python tools/init_env.py
echo "App: http://localhost:8000/app  Client: /app/#/client  Hack: /app/#/hack"
exec .venv/bin/python -m uvicorn thiqa.api:app --host 0.0.0.0 --port 8000
