# ──────────────────────────────────────────────────────────────────────────
# SketchPad Model Template
#
# GETTING STARTED:
#   1. cp -r models/_template models/<your_feature_name>
#   2. Edit manifest.json  — set name and description
#   3. Edit requirements.txt — add your dependencies
#   4. Implement process() below
#   5. ./scripts/setup_model.sh <your_feature_name>
#   6. Restart the backend — your model appears in the dropdown
# ──────────────────────────────────────────────────────────────────────────

from PIL import Image


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
        # ── Your model logic here ──────────────────────────────────────────

        return {
            "text": f'You said: "{prompt}". Replace this with your model output.',
            "image": None,  # return a PIL Image here to update the canvas
        }
