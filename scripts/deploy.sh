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

# ── 5. Restart backend ────────────────────────────────────────────────────
echo ""
echo "--- Restarting backend ---"
sudo systemctl restart sketchpad
sleep 2
if sudo systemctl is-active --quiet sketchpad; then
    echo "  Backend is running."
else
    echo "  WARNING: Backend failed to start."
    echo "  Check logs: sudo journalctl -u sketchpad -n 50"
    exit 1
fi

echo ""
echo "=== Deploy complete ==="
echo ""
echo "Useful commands:"
echo "  Status:  sudo systemctl status sketchpad"
echo "  Logs:    sudo journalctl -u sketchpad -f"
echo "  Nginx:   sudo systemctl status nginx"
