# Diffusion Diva — image editing via OpenAI gpt-image-1
#
# Setup:
#   1. Add credits at platform.openai.com/settings/billing
#   2. Copy .env.example to .env and paste your key: OPENAI_API_KEY=sk-...
#
# Speed: ~5–10 seconds per image

from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path

from PIL import Image

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)


class SketchPadModel:
    def process(self, image: Image.Image | None, prompt: str) -> dict:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {
                "text": (
                    "OPENAI_API_KEY not set.\n"
                    "Add it to models/diffusion_diva/.env:\n"
                    "  OPENAI_API_KEY=sk-..."
                ),
                "image": None,
            }

        if image is None:
            return {"text": "Please upload an image to the canvas first.", "image": None}

        if not prompt.strip():
            return {"text": "Please describe what you want to change.", "image": None}

        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        buf = BytesIO()
        image.convert("RGBA").save(buf, format="PNG")
        buf.seek(0)
        buf.name = "image.png"

        response = client.images.edit(
            model="gpt-image-1",
            image=buf,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )

        result_bytes = base64.b64decode(response.data[0].b64_json)
        result_image = Image.open(BytesIO(result_bytes)).convert("RGB")

        if result_image.size != image.size:
            result_image = result_image.resize(image.size, Image.LANCZOS)

        return {
            "text": f'Applied: "{prompt}"',
            "image": result_image
        }
