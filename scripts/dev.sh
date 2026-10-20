#!/usr/bin/env bash
# Modo desarrollo en Linux/macOS (Windows es la plataforma principal: usá scripts\start-dev.ps1).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; }
.venv/bin/python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8765 &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd "$ROOT/apps/web"
[ -d node_modules ] || npm install --no-fund --no-audit
npm run dev
