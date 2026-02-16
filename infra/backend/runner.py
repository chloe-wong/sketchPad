#!/usr/bin/env python3
"""
SketchPad model runner — infrastructure file, do not modify.

Called by the backend to execute a model inside its own venv.

Usage:
    python runner.py --model-dir <path_to_model_dir>

stdin:  JSON {"image": "<base64>|null", "prompt": "<string>"}
stdout: JSON {"text": "<string>", "image": "<base64>|null"}
"""

import sys
import json
import base64
import argparse
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    args = parser.parse_args()

    model_dir = Path(args.model_dir).resolve()
    sys.path.insert(0, str(model_dir))

    try:
        from model import SketchPadModel
    except ImportError as e:
        _fail(f"Could not import SketchPadModel from {model_dir}/model.py: {e}")

    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _fail(f"Invalid JSON input: {e}")

    # Decode image if provided
    image = None
    if data.get("image"):
        try:
            from PIL import Image
            from io import BytesIO
            image = Image.open(BytesIO(base64.b64decode(data["image"])))
        except Exception as e:
            _fail(f"Could not decode input image: {e}")

    # Run the model
    try:
        model_instance = SketchPadModel()
        result = model_instance.process(image=image, prompt=data.get("prompt", ""))
    except Exception as e:
        _fail(f"Model raised an exception: {e}\n{traceback.format_exc()}")

    # Build output
    output = {"text": result.get("text", ""), "image": None}

    if result.get("image") is not None:
        try:
            from io import BytesIO
            buf = BytesIO()
            result["image"].save(buf, format="PNG")
            output["image"] = base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            output["text"] += f"\n[Warning: could not encode output image: {e}]"

    print(json.dumps(output), flush=True)


def _fail(message: str):
    print(json.dumps({"error": message, "text": "", "image": None}), flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
