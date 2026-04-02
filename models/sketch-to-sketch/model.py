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
from controlnet_aux import HEDdetector
from diffusers import (
    ControlNetModel,
    EulerAncestralDiscreteScheduler,
    StableDiffusionControlNetPipeline
)
import numpy as np
import torch


class SketchPadModel:
    def __init__(self) -> None:
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        controlnet = ControlNetModel.from_pretrained(
            'vsanimator/sketch-a-sketch'
        ).to(self.device)
        self.pipe = StableDiffusionControlNetPipeline.from_pretrained(
            'runwayml/stable-diffusion-v1-5',
            controlnet=controlnet
        ).to(self.device)

        self.hed = HEDdetector.from_pretrained(
            'lllyasviel/Annotators'
        ).to(self.device)

        self.num_images = 1
        self.res = (190,190)

        self.pipe.safety_checker = None
        self.pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(self.pipe.scheduler.config)

    
    def _preprocess_sketch(self, curr_sketch):
        if curr_sketch is None:
            return np.full((*self.res, 3), 255, dtype=np.uint8)

        if isinstance(curr_sketch, dict):
            curr_sketch = curr_sketch.get('composite', curr_sketch)
            
        return np.array(curr_sketch).astype(np.uint8)


    def run_sketching(self, prompt, negative_prompt, curr_sketch):

        processed_canvas = self._preprocess_sketch(curr_sketch)
        to_return = []

        for k in range(self.num_images):
            seed = np.random.randint(1000000)

            new_image = self.sketch(prompt, negative_prompt, curr_sketch, seed=seed, num_steps=2)
            to_return.append(new_image)

        feedback_sketch = self.feedback_logic(to_return, processed_canvas)

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
            generator=generator,
            controlnet_conditioning_scale=1.0
        ).images


        return images[0]
    
    def feedback_logic(self, ai_images, current_canvas):
        hed_results = [self.hed(img, scribble=True) for img in ai_images]
    
        # 2. Average the edges (results in white lines on black background)
        avg_hed = np.mean([np.array(img) for img in hed_results], axis=0)
        
        # 3. Invert to get black lines on white background
        inverted_ai_lines = 255.0 - avg_hed
        
        # 4. Lighten the AI lines so they look like "pencil guides"
        # (Values closer to 255 are whiter/fainter)
        pencil_guides = np.clip(inverted_ai_lines + 50, 0, 255)
        
        # 5. Multiply with user canvas (Like 'Multiply' layer in Photoshop)
        # This keeps user's dark ink but adds the AI's light pencil guides
        final_sketch = (current_canvas.astype(float) / 255.0) * (pencil_guides / 255.0)
        
        return Image.fromarray(np.uint8(final_sketch * 255.0))



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
        # ── Your model logic here ──────────────────────────────────────────

        result = self.run_sketching(prompt=prompt,negative_prompt=self.generate_negative_prompt(prompt),curr_sketch= image)
        
        

        return {
            "text": f'You said: "{prompt}"',
            "image":result[-1],
        }
