import os
from PIL import Image
import numpy as np
from model import SketchPadModel

# Import your class - change 'your_filename' to whatever your script is named
# from your_filename import SketchPadModel 

def test_run():
    print("🚀 Initializing model (this might take a minute)...")
    model = SketchPadModel()

    # 1. CREATE A MOCK SKETCH
    # Let's draw a simple black square on a white background to test ControlNet
    test_canvas = np.full((512, 512, 3), 255, dtype=np.uint8)
    test_canvas[100:400, 100:400, :] = 0  # A black box
    sketch_pil = Image.fromarray(test_canvas)
    
    prompt = "a minimalist apartment, high quality anime style"
    
    print(f"🎨 Running inference with prompt: '{prompt}'...")
    
    # 2. CALL THE PROCESS METHOD
    # This mimics exactly what the backend would do
    output = model.process(sketch_pil, prompt)

    # 3. VERIFY AND SAVE OUTPUTS
    print(f"📝 Backend Feedback: {output['text']}")
    
    if output['image'] is not None:
        output['image'].save("test_output_main.png")
        print("✅ Main output saved to 'test_output_main.png'")
    
    # Optional: Test the full run_sketching to see all 3 variants + feedback
    print("🔄 Testing multi-image generation...")
    all_results = model.run_sketching(
        prompt, 
        model.generate_negative_prompt(prompt), 
        sketch_pil
    )
    
    # Save all variants
    for i, img in enumerate(all_results[:-1]): # The AI images
        img.save(f"variant_{i}.png")
    
    all_results[-1].save("feedback_loop.png") # The HED feedback sketch
    print("✨ All test images saved to your folder!")

if __name__ == "__main__":
    try:
        test_run()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")