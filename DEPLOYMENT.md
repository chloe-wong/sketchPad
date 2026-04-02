# SketchPad Deployment Guide

## Overview

SketchPad runs on an AWS EC2 instance that you **start before a demo and stop afterward**. You only pay for compute time while the instance is running (~$0.53/hr for the GPU instance), plus a small ongoing storage cost (~$4–8/month for the disk).

---

## One-Time AWS Setup

### 1. Launch an EC2 Instance

1. Go to **AWS Console → EC2 → Launch Instance**
2. **AMI:** Choose **"Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)"** — search for it under "AWS Marketplace AMIs". This comes with CUDA pre-installed, which the GPU model requires.
3. **Instance type:** `g4dn.xlarge` (1x NVIDIA T4 GPU, 4 vCPU, 16GB RAM)
4. **Storage:** 100 GB gp3 (edit the root volume under "Configure storage")
5. **Key pair:** Create a new key pair, download the `.pem` file, keep it safe — you need it to SSH in
6. **Security group — open these ports:**
   - Port 22 (SSH): your IP only (select "My IP" in the dropdown)
   - Port 80 (HTTP): `0.0.0.0/0` (public — this is what users visit)
7. Launch the instance.

### 2. Assign an Elastic IP (Important)

Without this, the server's public IP changes every time you start/stop the instance.

1. Go to **EC2 → Elastic IPs → Allocate Elastic IP**
2. Once allocated, click **Actions → Associate Elastic IP**
3. Associate it with your new instance
4. This IP is now permanent — use it everywhere (DNS, sharing with users, etc.)
5. **Cost:** Free while associated with a running instance. $0.005/hr if the instance is stopped — release it if you're done with the project entirely.

### 3. (Optional) Set Up a Domain

If you have a domain, point an A record at the Elastic IP. Otherwise, users can just use the raw IP address (`http://<elastic-ip>`).

---

## First-Time Server Setup

Do this once after launching the instance.

### 1. SSH into the instance

```bash
chmod 400 /path/to/your-key.pem
ssh -i /path/to/your-key.pem ubuntu@<elastic-ip>
```

### 2. Clone the repo

```bash
git clone https://github.com/<your-org>/sketchPad.git
cd sketchPad
```

### 3. Run the setup script

```bash
chmod +x scripts/*.sh
./scripts/server_setup.sh
```

This script (takes 5–15 minutes):
- Installs Python, Node.js 20, and Nginx
- Creates the backend venv and installs its dependencies
- Creates venvs for all existing models and installs their dependencies
- Builds the React frontend
- Configures Nginx to serve the frontend and proxy API requests to the backend
- Sets up a systemd service so the backend starts automatically and restarts on crash

When it finishes, the site is live at `http://<elastic-ip>`.

---

## Demo Day Workflow

### Before the demo

1. **Start the EC2 instance** in the AWS Console (EC2 → Instances → select → Instance State → Start)
2. Wait ~1 minute for it to boot
3. SSH in and deploy any pending merged PRs:
   ```bash
   ssh -i /path/to/your-key.pem ubuntu@<elastic-ip>
   cd sketchPad
   ./scripts/deploy.sh
   ```
4. Verify the site works by visiting `http://<elastic-ip>` in your browser

### After the demo

1. **Stop the EC2 instance** in the AWS Console (Instance State → Stop)
2. You stop paying for compute immediately. The disk persists.

---

## Deploying a New Model (after merging a PR)

> Always stop public traffic (or just do this on a non-demo day) since the backend restarts briefly.

```bash
ssh -i /path/to/your-key.pem ubuntu@<elastic-ip>
cd sketchPad
./scripts/deploy.sh
```

`deploy.sh` automatically:
1. Pulls the latest code from `main`
2. Detects any new model folders (those without a `.venv`) and runs `setup_model.sh` for them
3. Updates backend dependencies
4. Rebuilds the frontend
5. Restarts the backend service

The new model will appear in the UI dropdown immediately after the restart.

---

## Developer Guide: Adding a New Model

> Only touch your own `models/<your_feature>/` folder. Never modify `infra/` or another developer's model folder.

### Steps

```bash
# 1. Copy the template
cp -r models/_template models/<your_feature>

# 2. Fill in metadata
#    Edit: models/<your_feature>/manifest.json
#      - "name": display name shown in the UI dropdown
#      - "description": one-line description

# 3. Add your dependencies
#    Edit: models/<your_feature>/requirements.txt

# 4. Implement your model
#    Edit: models/<your_feature>/model.py
#    The only requirement: implement SketchPadModel.process()

# 5. Set up your local venv and test
./scripts/setup_model.sh <your_feature>
./scripts/start.sh   # visit http://localhost:5173

# 6. Open a PR — only your models/<your_feature>/ folder should be changed
```

### The model interface

```python
from PIL import Image

class SketchPadModel:
    def process(self, image: Image.Image | None, prompt: str) -> dict:
        # image: the current canvas as a PIL Image, or None if no image uploaded
        # prompt: the user's text input
        # Return: dict with "text" (str) and "image" (PIL.Image or None)
        #   - "text": the assistant's reply shown in the chat
        #   - "image": a new PIL Image to replace the canvas, or None to leave it unchanged
        return {"text": "your response here", "image": None}
```

### PR checklist

- [ ] `models/<your_feature>/manifest.json` exists with `name` and `description`
- [ ] `models/<your_feature>/requirements.txt` lists all dependencies
- [ ] `models/<your_feature>/model.py` contains a `SketchPadModel` class with a `process` method
- [ ] Tested locally with `./scripts/start.sh`
- [ ] PR only touches `models/<your_feature>/`

---

## Updating a Model's Dependencies

If a developer updates their `requirements.txt` after the model is already set up on the server, the new deps won't install automatically (the venv already exists). To update:

```bash
ssh -i /path/to/your-key.pem ubuntu@<elastic-ip>
cd sketchPad
git pull origin main
# Delete the existing venv so deploy.sh treats it as new and reinstalls
rm -rf models/<model_name>/.venv
./scripts/deploy.sh
```

---

## Troubleshooting

### Backend not starting

```bash
sudo journalctl -u sketchpad -n 50   # last 50 log lines
sudo systemctl status sketchpad
```

### Nginx errors

```bash
sudo nginx -t                              # test config syntax
sudo tail -f /var/log/nginx/error.log
sudo systemctl status nginx
```

### A model isn't appearing in the dropdown

The backend only discovers models at startup. After adding a new model and running `deploy.sh`, the backend restarts and picks it up. If it's still missing:
1. Check the model folder has `model.py` and a `.venv`
2. Check `models/<name>/manifest.json` is valid JSON
3. Check backend logs: `sudo journalctl -u sketchpad -n 50`

### Model times out

The backend allows up to 10 minutes per model run. If a model consistently times out, the issue is in the model code itself — check it locally first.

### SSH connection refused

The instance may still be booting. Wait 60 seconds and try again. If it persists, check the Security Group has port 22 open to your IP.

---

## Cost Summary

| Item | Cost |
|---|---|
| EC2 `g4dn.xlarge` compute | ~$0.53/hr (only while running) |
| EBS storage (100 GB gp3) | ~$8/month (always) |
| Elastic IP (while stopped) | $0.005/hr |
| **Typical demo day (8hrs)** | **~$12–13 total** |
| **Monthly (stopped most of time)** | **~$8–10** |

To minimize cost: stop the instance after every demo. Release the Elastic IP if the project ends.
