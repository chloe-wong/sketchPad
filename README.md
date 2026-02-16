# SketchPad

An AI-powered art assistant with a pluggable model system. Team members build models in isolation inside `models/`, and the shared chat UI lets users switch between tools while keeping image context.

---

## First-time setup

### 1. Backend
```bash
./scripts/setup_backend.sh
```

### 2. Frontend
```bash
cd infra/frontend && npm install
```

### 3. Start everything
```bash
./scripts/start.sh
```

Open **http://localhost:5173**

---

## Adding a new model

```bash
# 1. Copy the template
cp -r models/_template models/my_feature

# 2. Set up its venv
./scripts/setup_model.sh my_feature
```

Then edit the three files inside `models/my_feature/`:

| File | What to do |
|------|-----------|
| `manifest.json` | Set `name` and `description` (shown in the UI dropdown) |
| `requirements.txt` | Add your Python dependencies |
| `model.py` | Implement `SketchPadModel.process()` |

Restart the backend — your model appears in the dropdown automatically.

---

## Model interface

This is the **only** thing contributors need to implement:

```python
from PIL import Image

class SketchPadModel:
    def process(self, image: Image.Image | None, prompt: str) -> dict:
        """
        Args:
            image  : Current canvas as a PIL Image, or None if not uploaded.
            prompt : User's text request.

        Returns:
            "text"  (str)             — feedback / explanation shown in chat
            "image" (PIL.Image | None) — modified canvas, or None if unchanged
        """
        return {
            "text": "Your response here",
            "image": None,  # or a PIL Image
        }
```

**Rules:**
- Only work inside your `models/<your_feature>/` folder
- Do not modify anything in `infra/` or other model folders
- Add all dependencies to your own `requirements.txt`

---

## Project structure

```
sketchpad/
├── infra/
│   ├── backend/       ← FastAPI server (do not modify)
│   └── frontend/      ← React chat UI (do not modify)
├── models/
│   ├── _template/     ← Copy this to start a new model
│   └── <your_model>/  ← Your work lives here
└── scripts/
    ├── setup_backend.sh
    ├── setup_model.sh
    └── start.sh
```
