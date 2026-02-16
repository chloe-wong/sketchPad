#!/bin/bash
# Start the SketchPad backend and frontend dev servers.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$ROOT/infra/backend/.venv/bin/uvicorn" ]; then
  echo "Backend venv not found. Run: ./scripts/setup_backend.sh"
  exit 1
fi

if [ ! -d "$ROOT/infra/frontend/node_modules" ]; then
  echo "Frontend dependencies not installed. Run: cd infra/frontend && npm install"
  exit 1
fi

# Kill child processes on exit
trap 'kill $(jobs -p) 2>/dev/null' EXIT

echo "Starting backend on http://localhost:8000 ..."
(cd "$ROOT/infra/backend" && .venv/bin/uvicorn main:app --reload --port 8000) &

echo "Starting frontend on http://localhost:5173 ..."
(cd "$ROOT/infra/frontend" && npm run dev) &

wait
