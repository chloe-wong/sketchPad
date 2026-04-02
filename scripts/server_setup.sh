#!/bin/bash
# One-time setup for a fresh EC2 Ubuntu instance.
# Run this once after cloning the repo onto the server.
# Usage: ./scripts/server_setup.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NGINX_CONF="/etc/nginx/sites-available/sketchpad"
SERVICE_FILE="/etc/systemd/system/sketchpad.service"
CURRENT_USER="$(whoami)"

echo "=== SketchPad Server Setup ==="
echo "Repo root: $ROOT"
echo "Running as user: $CURRENT_USER"

# ── 1. System packages ────────────────────────────────────────────────────
echo ""
echo "--- Installing system packages ---"
sudo apt-get update -q
sudo apt-get install -y -q python3 python3-venv python3-pip nginx curl

# ── 2. Node.js 20 ─────────────────────────────────────────────────────────
echo ""
echo "--- Installing Node.js 20 ---"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y -q nodejs
else
    echo "  Node already installed: $(node --version)"
fi

# ── 3. Backend venv ───────────────────────────────────────────────────────
echo ""
echo "--- Setting up backend ---"
"$ROOT/scripts/setup_backend.sh"

# ── 4. All existing model venvs ───────────────────────────────────────────
echo ""
echo "--- Setting up model venvs ---"
for model_dir in "$ROOT"/models/*/; do
    name=$(basename "$model_dir")
    [[ "$name" == _* || "$name" == .* ]] && continue
    echo "  Setting up: $name"
    "$ROOT/scripts/setup_model.sh" "$name"
done

# ── 5. Frontend build ─────────────────────────────────────────────────────
echo ""
echo "--- Building frontend ---"
cd "$ROOT/infra/frontend"
npm install --silent
npm run build
cd "$ROOT"

# ── 6. Nginx config ───────────────────────────────────────────────────────
echo ""
echo "--- Configuring Nginx ---"
sudo tee "$NGINX_CONF" > /dev/null <<NGINX
server {
    listen 80;
    server_name _;

    # Allow larger image uploads (base64-encoded images can be several MB)
    client_max_body_size 50m;

    # Serve the built React frontend
    root $ROOT/infra/frontend/dist;
    index index.html;

    # Proxy API routes to FastAPI backend
    location /models {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /session {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        # Must exceed the 600s model timeout so Nginx doesn't cut the connection first
        proxy_read_timeout 620s;
        proxy_send_timeout 620s;
    }

    # SPA fallback — all other paths serve index.html
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX

sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/sketchpad
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
echo "  Nginx configured and running."

# ── 7. Systemd service for FastAPI backend ────────────────────────────────
echo ""
echo "--- Configuring systemd service ---"
sudo tee "$SERVICE_FILE" > /dev/null <<SERVICE
[Unit]
Description=SketchPad Backend
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$ROOT/infra/backend
ExecStart=$ROOT/infra/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable sketchpad
sudo systemctl start sketchpad
sleep 2

if sudo systemctl is-active --quiet sketchpad; then
    echo "  Backend service is running."
else
    echo "  ERROR: Backend service failed to start."
    echo "  Check logs: sudo journalctl -u sketchpad -n 50"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup complete ==="
echo ""
echo "The site is now live on port 80."
echo ""
echo "Useful commands:"
echo "  Backend status:  sudo systemctl status sketchpad"
echo "  Backend logs:    sudo journalctl -u sketchpad -f"
echo "  Nginx status:    sudo systemctl status nginx"
echo "  Nginx logs:      sudo tail -f /var/log/nginx/error.log"
echo ""
echo "To deploy future changes: ./scripts/deploy.sh"
