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

import sys
import os
import re
import tempfile
import traceback
import io
import base64
from PIL import Image

CURR_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(CURR_DIR)
from utils.my_ganmut import GANmut

class SketchPadModel:
    def __init__(self):
        """
        Initialize model, loads into memory only when backend starts, not per request
        """
        weights_path = os.path.join(
            CURR_DIR,
            'learned_generators',
            'lin_2d',
            '1000000-G.ckpt'
        )
        old_stdout = sys.stdout
        sys.stdout = sys.stderr
        try:
            self.G = GANmut(G_path=weights_path, model='linear')
        finally:
            sys.stdout = old_stdout
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
        try:
            if image is None:
                return {
                    "text": "No image. Please upload an image with a face.",
                    "image": None
                }
            theta, rho = self._parse_prompt(prompt)

            # set up temporary directory

            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = os.path.join(temp_dir, "workspace")
                os.makedirs(workspace)

                input_path = os.path.join(workspace, "input_face.jpg")
                # save image
                image.convert("RGB").save(input_path)

                #temporarily hijack cwd
                old_cwd = os.getcwd()
                os.chdir(workspace)

                original_stdout = sys.stdout
                sys.stdout = sys.stderr

                try:
                    # GANmut inference
                    self.G.emotion_edit(img_path=input_path, theta=theta, rho=rho, save=True)
                except Exception as inner_e:
                    sys.stderr.write(f"GANmut Error: {str(inner_e)}\n")
                    return {
                        "text": f"Could not find a face. Error: {str(inner_e)}",
                        "image": None
                    }
                finally:
                    sys.stdout = original_stdout
                    os.chdir(old_cwd)
                ganmut_output_dir = os.path.join(temp_dir, "edited_images") 
                if not os.path.exists(ganmut_output_dir):
                    sys.stderr.write("ERROR: GANmut did not create the edited_images folder\n")
                    return {"text": "Error: Image generation failed.", "image": None}   

                generated_files = os.listdir(ganmut_output_dir)
                if not generated_files:
                    return {"text": "Error: Folder created, but no image inside.", "image": None}
                
                sys.stderr.write(f"DEBUG: All files before filter -> {generated_files}\n")
                # filter out original iamge
                edited_files = [f for f in generated_files if not f.startswith('original_')]

                sys.stderr.write(f"DEBUG: Files after filter -> {edited_files}\n")
                if not edited_files:
                    return {"text": "Error: Only original image found, edited image missing.", "image": None}
                actual_output_path = os.path.join(ganmut_output_dir, edited_files[0])
                sys.stderr.write(f"DEBUG: found GANmut output at {actual_output_path}\n")
                result_image = Image.open(actual_output_path).copy()
                result_image.load()

                return {
                    "text": f"Applied theta={theta}, rho={rho}.",
                    "image": result_image
                }
        except Exception as e:
            sys.stderr.write(f"CRASH: {str(e)}\n")
            return {
                "text": f"Backend Crash: {str(e)}",
                "image": None
            }
    def _parse_prompt(self, prompt: str) -> tuple[float, float]:
        """
        Extract theta (angle) and rho (intensity/strength) from prompt.
        """
        # can be theta=, angle=, rho=, strength=
        theta_match = re.search(r'(?:theta|angle)[=:]\s*(-?\d*\.?\d+)', prompt.lower())
        rho_match = re.search(r'(?:rho|strength|intensity)[=:]\s*(-?\d*\.?\d+)', prompt.lower())

        # default to 0 angle, 0 strength (neutral face)
        theta_val = float(theta_match.group(1)) if theta_match else 0.0
        rho_val = float(rho_match.group(1)) if rho_match else 0.0

        # rho must be between 0.0 and 1.0
        rho_val = max(0.0, min(1.0, rho_val))

        return theta_val, rho_val