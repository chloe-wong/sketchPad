#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Setting up backend venv..."
python3 -m venv "$ROOT/infra/backend/.venv"
"$ROOT/infra/backend/.venv/bin/pip" install --quiet --upgrade pip
"$ROOT/infra/backend/.venv/bin/pip" install -r "$ROOT/infra/backend/requirements.txt"
echo "Backend ready."
