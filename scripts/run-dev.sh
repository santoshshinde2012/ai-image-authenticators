#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
uv run uvicorn ai_image_authenticator.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
cd "$ROOT/apps/web"
npm run dev -- --host 127.0.0.1 --port 5173
