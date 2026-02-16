"""
SketchPad backend — infrastructure file, do not modify.
"""

import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from model_registry import ModelRegistry

# ── Paths ──────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent
MODELS_DIR = REPO_ROOT / "models"
RUNNER_PATH = BACKEND_DIR / "runner.py"

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(title="SketchPad API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = ModelRegistry(MODELS_DIR)

# In-memory sessions (sufficient for local dev)
_sessions: dict[str, dict] = {}


# ── Models ─────────────────────────────────────────────────────────────────
@app.get("/models")
def list_models():
    return registry.list_models()


# ── Sessions ───────────────────────────────────────────────────────────────
@app.post("/session")
async def create_session(file: Optional[UploadFile] = File(None)):
    session_id = str(uuid.uuid4())[:8]
    image_b64 = None

    if file:
        data = await file.read()
        image_b64 = base64.b64encode(data).decode()

    _sessions[session_id] = {
        "id": session_id,
        "current_image": image_b64,
        "messages": [],
    }

    return {"session_id": session_id, "has_image": image_b64 is not None}


@app.get("/session/{session_id}")
def get_session(session_id: str):
    session = _get_or_404(session_id)
    return {
        "session_id": session_id,
        "has_image": session["current_image"] is not None,
        "current_image": session["current_image"],
        "messages": session["messages"],
    }


@app.post("/session/{session_id}/image")
async def update_image(session_id: str, file: UploadFile = File(...)):
    """Replace the canvas image without clearing the chat history."""
    session = _get_or_404(session_id)
    data = await file.read()
    session["current_image"] = base64.b64encode(data).decode()
    return {"ok": True}


# ── Messages ───────────────────────────────────────────────────────────────
class MessageRequest(BaseModel):
    model_id: str
    prompt: str


@app.post("/session/{session_id}/message")
async def send_message(session_id: str, req: MessageRequest):
    session = _get_or_404(session_id)

    model = registry.get_model(req.model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{req.model_id}' not found")

    result = await _run_model(
        model_dir=str(model["path"]),
        image_b64=session["current_image"],
        prompt=req.prompt,
    )

    # Update canvas if model returned a new image
    if result.get("image"):
        session["current_image"] = result["image"]

    session["messages"].append({"role": "user", "text": req.prompt, "image": None})
    session["messages"].append(
        {"role": "assistant", "text": result.get("text", ""), "image": result.get("image")}
    )

    return {
        "text": result.get("text", ""),
        "image": result.get("image"),
        "session_id": session_id,
    }


# ── Helpers ────────────────────────────────────────────────────────────────
def _get_or_404(session_id: str) -> dict:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _run_model(model_dir: str, image_b64: Optional[str], prompt: str) -> dict:
    venv_python = Path(model_dir) / ".venv" / "bin" / "python"

    if not venv_python.exists():
        model_name = Path(model_dir).name
        raise HTTPException(
            status_code=500,
            detail=(
                f"Venv not found for model '{model_name}'. "
                f"Run: ./scripts/setup_model.sh {model_name}"
            ),
        )

    input_payload = json.dumps({"image": image_b64, "prompt": prompt})

    proc = await asyncio.create_subprocess_exec(
        str(venv_python),
        str(RUNNER_PATH),
        "--model-dir",
        model_dir,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input_payload.encode()),
            timeout=600,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail="Model timed out after 10 minutes")

    if proc.returncode != 0:
        # Error may be in stdout (JSON from runner._fail) or stderr (unhandled exception)
        err = stderr.decode().strip()
        try:
            data = json.loads(stdout.decode())
            err = data.get("error") or err
        except Exception:
            pass
        print(f"\n[MODEL ERROR — {Path(model_dir).name}]\n{err}\n")
        raise HTTPException(status_code=500, detail=err)

    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Model returned invalid JSON")
