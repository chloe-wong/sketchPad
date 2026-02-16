"""
Discovers and registers SketchPad models from the models/ directory.
Infrastructure file — do not modify.
"""

import json
from pathlib import Path
from typing import Optional


class ModelRegistry:
    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self._models: dict[str, dict] = {}

    def _discover(self):
        self._models = {}
        if not self.models_dir.exists():
            return

        for model_dir in sorted(self.models_dir.iterdir()):
            # Skip hidden folders, _template, and non-directories
            if not model_dir.is_dir() or model_dir.name.startswith("_"):
                continue

            model_py = model_dir / "model.py"
            if not model_py.exists():
                continue

            model_id = model_dir.name
            manifest_path = model_dir / "manifest.json"

            if manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)
                    name = manifest.get("name", model_id)
                    description = manifest.get("description", "")
                except (json.JSONDecodeError, OSError):
                    name = model_id.replace("_", " ").title()
                    description = ""
            else:
                name = model_id.replace("_", " ").title()
                description = ""

            self._models[model_id] = {
                "id": model_id,
                "name": name,
                "description": description,
                "path": model_dir,
            }

    def list_models(self) -> list[dict]:
        self._discover()
        return [
            {"id": m["id"], "name": m["name"], "description": m["description"]}
            for m in self._models.values()
        ]

    def get_model(self, model_id: str) -> Optional[dict]:
        self._discover()
        return self._models.get(model_id)
