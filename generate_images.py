"""
AI Image Generation Pipeline - Step 2
Generates styled lifestyle product images using Gemini Image Generation API.
Traverses hierarchical category structure and applies appropriate prompts.
"""

import os
import json
import base64
import shutil
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO
from tqdm import tqdm

# ============================================================================
# Configuration
# ============================================================================

# API Key (get from: https://aistudio.google.com/apikey)
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# Model selection (auto-switches based on TEST_MODE)
GEMINI_MODEL_TEST = "gemini-2.5-flash-image"  # Fast & cheap for testing (~$0.04/image)
GEMINI_MODEL_PRODUCTION = "gemini-3-pro-image-preview"  # Best quality (~$0.13/image)

# Technical settings
INPUT_FOLDER = "aquateak_products"
OUTPUT_FOLDER = "generated_images"
CATEGORY_CONFIG = "category_prompts.json"
LOG_FILE = "generation_log.txt"
REQUEST_DELAY = 5.0  # Increased to avoid rate limits
TEST_MODE = True  # Set False for production run

# ============================================================================
# Helper Functions
# ============================================================================

def log_error(console_msg, log_msg):
    """Log error to console and file."""
    tqdm.write(f"  ✗ {console_msg}")
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{log_msg}\n")
    except Exception as e:
        tqdm.write(f"  Warning: Couldn't write to log: {e}")


def load_config():
    """Load category prompts from JSON."""
    try:
        with open(CATEGORY_CONFIG, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        raise


def image_to_base64(image_path):
    """Convert image to base64."""
    with open(image_path, 'rb') as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')


def base64_to_image(base64_string):
    """Convert base64 to PIL Image."""
    image_data = base64.b64decode(base64_string)
    return Image.open(BytesIO(image_data))


def call_gemini_api(prompt, input_image_path, api_key, model, aspect_ratio="1:1", image_size="2K"):
    """Call Gemini API to generate styled image with retry logic."""
    import time
    
    max_retries = 3
    base_delay = 10  # Start with 10 second delay
    
    for attempt in range(max_retries):
        try:
            api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            image_base64 = image_to_base64(input_image_path)
            
            headers = {
                "x-goog-api-key": api_key,
                "Content-Type": "application/json"
            }
            
            # Build image config (imageSize only supported by Pro model)
            image_config = {"aspectRatio": aspect_ratio}
            if "gemini-3" in model:  # Only Pro model supports imageSize
                image_config["imageSize"] = image_size
            
            body = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}
                    ]
                }],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": image_config
                }
            }
            
            response = requests.post(api_endpoint, headers=headers, json=body, timeout=60)
            response.raise_for_status()
            result = response.json()
            
            if "candidates" in result and len(result["candidates"]) > 0:
                parts = result["candidates"][0].get("content", {}).get("parts", [])
                for part in parts:
                    if "inlineData" in part:
                        image_data = part["inlineData"].get("data")
                        if image_data:
                            return base64_to_image(image_data)
            
            raise Exception("No image data in API response")
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit error
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)  # Exponential backoff
                    tqdm.write(f"    ⏳ Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Rate limit exceeded after {max_retries} attempts. Wait and try again later.")
            else:
                raise Exception(f"HTTP {e.response.status_code}: {e}")
        except Exception as e:
            raise Exception(f"API call error: {e}")


def get_category_prompt(config, top_cat, mid_cat, granular_cat):
    """Navigate nested config to find category prompt."""
    try:
        base_prompt = config.get("base_prompt", "")
        cat_prompt = config["categories"][top_cat][mid_cat][granular_cat]["prompt"]
        return f"{base_prompt} {cat_prompt}"
    except KeyError:
        tqdm.write(f"  Warning: Prompt not found for {top_cat}/{mid_cat}/{granular_cat}")
        return config.get("base_prompt", "")


def generate_variants(product_path, prompt, output_subfolder, api_key, model, variants_per_image, aspect_ratio, image_size):
    """Generate AI variants for single product."""
    import time
    
    successful = 0
    failed = 0
    
    filename = os.path.basename(product_path)
    name_without_ext = os.path.splitext(filename)[0]
    file_ext = os.path.splitext(filename)[1]
    sku = name_without_ext.split(' - ')[0] if ' - ' in name_without_ext else 'UNKNOWN'
    
    # Copy original as v0
    try:
        original_dest = os.path.join(output_subfolder, f"v0 {name_without_ext}{file_ext}")
        shutil.copy2(product_path, original_dest)
    except Exception as e:
        log_error(f"Failed to copy original: {e}", f"{sku} - {name_without_ext}: Failed to copy - {e}")
    
    # Generate variants
    for variant_num in range(1, variants_per_image + 1):
        try:
            generated_image = call_gemini_api(prompt, product_path, api_key, model, aspect_ratio, image_size)
            
            if generated_image is None:
                raise Exception("API returned None")
            
            variant_filename = f"v{variant_num} {name_without_ext}.jpg"
            variant_path = os.path.join(output_subfolder, variant_filename)
            generated_image.save(variant_path, "JPEG", quality=95)
            
            successful += 1
            tqdm.write(f"    ✓ Generated v{variant_num}")
            
            if variant_num < variants_per_image:
                time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            failed += 1
            log_error(f"Variant v{variant_num} failed: {str(e)[:50]}", 
                     f"{sku} - {name_without_ext} - v{variant_num}: {e}")
    
    return successful, failed


def process_granular_category(category_path, prompt, output_path, api_key, model, variants_per_image, aspect_ratio, image_size):
    """Process all images in a granular category folder."""
    total_successful = 0
    total_failed = 0
    
    image_files = [f for f in os.listdir(category_path)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not image_files:
        return 0, 0
    
    # In TEST_MODE: process only 1 product per category
    # In PRODUCTION: process all products
    files_to_process = [image_files[0]] if TEST_MODE else image_files
    
    for image_file in tqdm(files_to_process, desc="    Processing images", leave=False, unit="img"):
        image_path = os.path.join(category_path, image_file)
        name_without_ext = os.path.splitext(image_file)[0]
        
        product_subfolder = os.path.join(output_path, name_without_ext)
        os.makedirs(product_subfolder, exist_ok=True)
        
        successful, failed = generate_variants(image_path, prompt, product_subfolder, 
                                              api_key, model, variants_per_image, aspect_ratio, image_size)
        
        total_successful += successful
        total_failed += failed
    
    return total_successful, total_failed


def main():
    """Main generation workflow."""
    print("="*60)
    print("AI Image Generation Pipeline - Step 2")
    print("="*60)
    
    # Validate API key
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("\n✗ ERROR: Please set GEMINI_API_KEY in generate_images.py")
        return
    
    if not os.path.exists(INPUT_FOLDER):
        print(f"\n✗ ERROR: Input folder '{INPUT_FOLDER}' not found")
        print("Run scraper.py first to create product images")
        return
    
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    if os.path.exists(OUTPUT_FOLDER):
        print(f"\nDeleting existing folder: {OUTPUT_FOLDER}/")
        shutil.rmtree(OUTPUT_FOLDER)
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    print(f"Created fresh output folder: {OUTPUT_FOLDER}/\n")
    
    # Select model based on TEST_MODE
    model = GEMINI_MODEL_TEST if TEST_MODE else GEMINI_MODEL_PRODUCTION
    
    # Load configuration
    try:
        config = load_config()
        
        # Get settings from JSON
        variants_per_image = config.get("variants_per_image", 3)
        aspect_ratio = config.get("aspect_ratio", "1:1")
        image_size = config.get("image_size", "2K")
        
        print(f"Loaded configuration from {CATEGORY_CONFIG}")
        print(f"Model: {model} ({'TEST' if TEST_MODE else 'PRODUCTION'})")
        print(f"Variants per image: {variants_per_image}")
        print(f"Aspect ratio: {aspect_ratio}")
        print(f"\n⚠️  NOTE: Visible watermarks will be added by Google")
        print(f"    Run watermark_removal.py after generation to remove them\n")
        
        if TEST_MODE:
            print(f"{'!'*60}")
            print("TEST MODE - Processing 1 product per category")
            print(f"Estimated cost: ~$3.60 (30 categories × 3 variants @ $0.04/image)")
            print(f"{'!'*60}\n")
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return
    
    grand_total_successful = 0
    grand_total_failed = 0
    
    # Traverse 3-level hierarchy
    for top_name in os.listdir(INPUT_FOLDER):
        top_path = os.path.join(INPUT_FOLDER, top_name)
        if not os.path.isdir(top_path):
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing: {top_name}")
        print(f"{'='*60}")
        
        for mid_name in os.listdir(top_path):
            mid_path = os.path.join(top_path, mid_name)
            if not os.path.isdir(mid_path):
                continue
            
            tqdm.write(f"\n  {mid_name}")
            
            for granular_name in os.listdir(mid_path):
                granular_path = os.path.join(mid_path, granular_name)
                if not os.path.isdir(granular_path):
                    continue
                
                output_path = os.path.join(OUTPUT_FOLDER, top_name, mid_name, granular_name)
                os.makedirs(output_path, exist_ok=True)
                
                # Get prompt for this category
                prompt = get_category_prompt(config, top_name, mid_name, granular_name)
                
                tqdm.write(f"    {granular_name}")
                
                successful, failed = process_granular_category(granular_path, prompt, output_path,
                                                              GEMINI_API_KEY, model, variants_per_image, aspect_ratio, image_size)
                
                grand_total_successful += successful
                grand_total_failed += failed
    
    total_variants = grand_total_successful + grand_total_failed
    success_rate = (grand_total_successful / total_variants * 100) if total_variants > 0 else 0
    
    summary = f"""
{'='*60}
GENERATION COMPLETE
{'='*60}
Successfully generated: {grand_total_successful} / {total_variants} ({success_rate:.1f}%)
Failed: {grand_total_failed}
Images saved to: {OUTPUT_FOLDER}/
Error log: {LOG_FILE}

⚠️  NEXT STEP: Run watermark_removal.py to clean images
{'='*60}
"""
    print(summary)
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n{summary}")
    except Exception as e:
        print(f"Warning: Couldn't write summary to log: {e}")


if __name__ == "__main__":
    main()