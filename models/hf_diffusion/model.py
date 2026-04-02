# ──────────────────────────────────────────────────────────────────────────
# SketchPad – Hugging Face Diffusion
#
# Generates images from text prompts using the HF Inference API.
#
# Setup:
#   1. Copy .env.example to .env and add your token: HF_API_TOKEN=hf_...
#   2. ./scripts/setup_model.sh hf_diffusion
# ──────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image
from huggingface_hub import InferenceClient

# Load .env from this model's directory
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)


class SketchPadModel:
    def process(self, image: Image.Image | None, prompt: str) -> dict:
        """
        Args:
            image  : The current canvas image as a PIL Image, or None if the
                     user hasn't uploaded one yet.
            prompt : The user's text request.

        Returns:
            A dict with two keys:
                "text"  (str)             — feedback / explanation for the user
                "image" (PIL.Image | None) — the modified image, or None if
                                             the canvas should stay unchanged
        """
        api_token = os.environ.get("HF_API_TOKEN")
        if not api_token:
            return {
                "text": (
                    "HF_API_TOKEN not set.\n"
                    "Add it to models/hf_diffusion/.env:\n"
                    "  HF_API_TOKEN=hf_..."
                ),
                "image": None,
            }

        if not prompt.strip():
            return {"text": "Please enter a prompt describing the image to generate.", "image": None}

        client = InferenceClient(token=api_token)
        model_id = "black-forest-labs/FLUX.1-schnell"

        try:
            # Call the HF Inference API — returns a PIL Image directly.
            generated_image: Image.Image = client.text_to_image(
                prompt=prompt,
                model=model_id,
            )

            return {
                "text": f'Generated image for: "{prompt}"',
                "image": generated_image,
            }

        except Exception as error:
            return {
                "text": f"⚠️ Image generation failed ({model_id}): {error}",
                "image": None,
            }
