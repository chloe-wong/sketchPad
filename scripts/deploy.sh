#!/bin/bash
# Deploy latest changes from main to the running server.
# Run this on the EC2 instance after SSHing in.
# Usage: ./scripts/deploy.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== SketchPad Deploy ==="

# ── 1. Pull latest code ────────────────────────────────────────────────────
echo ""
echo "--- Pulling latest code ---"
git -C "$ROOT" pull origin main
git -C "$ROOT" submodule update --init --recursive

# ── 2. Set up any new model venvs ──────────────────────────────────────────
# A model is "new" if its folder exists but has no .venv yet.
echo ""
echo "--- Checking for new models ---"
for model_dir in "$ROOT"/models/*/; do
    name=$(basename "$model_dir")
    # Skip _template and any hidden directories
    [[ "$name" == _* || "$name" == .* ]] && continue
    if [ ! -d "$model_dir/.venv" ]; then
        echo "  New model detected: $name — running setup..."
        "$ROOT/scripts/setup_model.sh" "$name"
    else
        echo "  $name — already set up, skipping."
    fi
done

# ── 3. Update backend dependencies ────────────────────────────────────────
# Handles the case where infra/backend/requirements.txt changed.
echo ""
echo "--- Updating backend dependencies ---"
"$ROOT/infra/backend/.venv/bin/pip" install -q --upgrade pip
"$ROOT/infra/backend/.venv/bin/pip" install -q -r "$ROOT/infra/backend/requirements.txt"

# ── 4. Rebuild frontend ────────────────────────────────────────────────────
echo ""
echo "--- Building frontend ---"
cd "$ROOT/infra/frontend"
npm install --silent
npm run build
cd "$ROOT"

echo ""
echo "=== Deploy complete ==="
echo "Restart the backend process to pick up changes."
