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
import os
from controlnet_aux import HEDdetector
from diffusers import (
    ControlNetModel,
    EulerAncestralDiscreteScheduler,
    StableDiffusionControlNetPipeline
)
import numpy as np
import torch
from datetime import datetime
import multiprocessing

class SketchPadModel:
    def __init__(self) -> None:
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        torch.set_num_threads(multiprocessing.cpu_count() // 2)
        controlnet = ControlNetModel.from_pretrained(
            'vsanimator/sketch-a-sketch'
        ).to(self.device)
        self.pipe = StableDiffusionControlNetPipeline.from_pretrained(
            'runwayml/stable-diffusion-v1-5',
            controlnet=controlnet
        ).to(self.device)
        # print("🚀 Loading ControlNet...", flush=True)

        self.pipe.load_lora_weights("latent-consistency/lcm-lora-sdv1-5")
        self.pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(self.pipe.scheduler.config)

        self.output_dir = "debug_outputs" 
        os.makedirs(self.output_dir, exist_ok=True)

        self.hed = HEDdetector.from_pretrained(
            'lllyasviel/Annotators'
        ).to(self.device)

        self.num_images = 3
        self.res = (512,512)
    
    def _preprocess_sketch(self, curr_sketch):
        if curr_sketch is None:
            return np.full((*self.res, 3), 255, dtype=np.uint8)

        if isinstance(curr_sketch, dict):
            curr_sketch = curr_sketch.get('composite', curr_sketch)
            
        return np.array(curr_sketch).astype(np.uint8)

    def _debug_save(self, image, prefix="gen"):
        """Saves image to local folder so you can see progress without the UI."""
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{self.output_dir}/{prefix}_{timestamp}.png"
        image.save(filename)
        # print(f"💾 Saved debug image to: {filename}", flush=True)


    def run_sketching(self, prompt, negative_prompt, curr_sketch):

        processed_canvas = self._preprocess_sketch(curr_sketch)
        to_return = []

        for k in range(self.num_images):
            # print(f"🎨 Starting Variant {k+1}/{self.num_images}...", flush=True)
            seed = np.random.randint(1000000)

            new_image = self.sketch(prompt, negative_prompt, processed_canvas, seed=seed, num_steps=20)
            self._debug_save(new_image, prefix=f"variant_{k}")
            to_return.append(new_image)

        # print("🔍 Running Feedback Logic (HED)...", flush=True)
        feedback_sketch = self.feedback_logic(to_return, processed_canvas)
        self._debug_save(feedback_sketch, prefix="feedback_final")

        return to_return + [feedback_sketch]



    def sketch(self, prompt, negative_prompt, curr_sketch, seed, num_steps):
        generator = torch.Generator(device=self.device)
        generator.manual_seed(seed)

        if isinstance(curr_sketch, Image.Image):
            curr_sketch = np.array(curr_sketch)
            
        curr_sketch_image = Image.fromarray(curr_sketch.astype(np.uint8)).convert('L')
        control_image = curr_sketch_image.convert('RGB').point(lambda p: 256 if p > 128 else 0)
        images = self.pipe(
            prompt,
            control_image,
            negative_prompt=negative_prompt,
            num_inference_steps=num_steps,
            guidance_scale=1.5,
            generator=generator,
            controlnet_conditioning_scale=0.8
        ).images


        return images[0]
    
    def feedback_logic(self, ai_images, current_canvas):
        try:
            hed_results = [self.hed(img, scribble=True) for img in ai_images]
            avg_hed = np.mean([np.array(img) for img in hed_results], axis=0)
            
            # Invert and lighten
            inverted_ai_lines = 255.0 - avg_hed
            pencil_guides = np.clip(inverted_ai_lines + 50, 0, 255)
            
            # CRITICAL: Match shapes exactly
            if isinstance(current_canvas, Image.Image):
                current_canvas = np.array(current_canvas)
                
            # Resize current_canvas to match the HED output dimensions
            h, w = pencil_guides.shape[:2]
            user_resized = np.array(Image.fromarray(current_canvas).resize((w, h)).convert("RGB"))
            
            # Perform the blend
            final_sketch = (user_resized.astype(float) / 255.0) * (pencil_guides / 255.0)
            return Image.fromarray(np.uint8(final_sketch * 255.0))
            
        except Exception as e:
            # print(f"❌ Feedback Logic Error: {e}", flush=True)
            # Fallback: just return the first AI image if math fails
            return ai_images[0]



    def reset(self):
        blank_canvas = np.full((*self.res, 3), 255, dtype=np.uint8)
        return blank_canvas


    def generate_negative_prompt(self, prompt):
        '''
        TODO: automate negative prompt generation 
        '''
        return "low quality, worst quality, blurry, distorted, grainy, low resolution, extra fingers, deformed hands, watermark, text, signature, out of frame, cropped, messy lines, oversaturated"


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
        if image is None:
            return {"text": "Please upload an image to the canvas first.", "image": None}

        if not prompt.strip():
            return {"text": "Please describe what you want to change.", "image": None}
        result = self.run_sketching(prompt=prompt,negative_prompt=self.generate_negative_prompt(prompt),curr_sketch= image)
            
        output_image = result[-1]
        
        if not isinstance(output_image, Image.Image):
            # Force conversion if it's a numpy array
            output_image = Image.fromarray(np.uint8(output_image))

        

        return {
            "text": f"Success: {prompt}",
            "image": output_image, # The framework handles turning this into a string
        }

        # ── Your model logic here ──────────────────────────────────────────
        try:
            result = self.run_sketching(prompt=prompt,negative_prompt=self.generate_negative_prompt(prompt),curr_sketch= image)
            
            output_image = result[-1]
            
            if not isinstance(output_image, Image.Image):
                # Force conversion if it's a numpy array
                output_image = Image.fromarray(np.uint8(output_image))

            

            return {
                "text": f"Success: {prompt}",
                "image": output_image, # The framework handles turning this into a string
            }

        except Exception as e:
            print(f"🔥 CRITICAL ERROR: {e}", flush=True)
            # Return a valid JSON dictionary even if the AI fails
            return {
                "text": f"Error occurred: {str(e)}",
                "image": image # Return original sketch so UI doesn't break
            }
