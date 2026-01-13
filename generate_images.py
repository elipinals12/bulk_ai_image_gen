"""
AI Image Generation Pipeline - Step 2
Generates styled lifestyle product images using Gemini Image Generation API.
Traverses hierarchical category structure and applies appropriate prompts.
Generates 5 shot types: room, tight, cropped, white, white-in-use.

FIXED: 
- SKU extraction verified (works correctly)
- New naming convention with leading numbers for alphabetical sorting
- Output format: "sku - [category#] [type] vX.jpg"
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

# API Key (loaded from apikey.txt in current directory)
def load_api_key():
    """Load API key from apikey.txt file."""
    try:
        with open('apikey.txt', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("\n✗ ERROR: apikey.txt not found!")
        print("Create a file named 'apikey.txt' in the current directory")
        print("Get your API key from: https://aistudio.google.com/apikey")
        return None
    except Exception as e:
        print(f"\n✗ ERROR: Could not read apikey.txt: {e}")
        return None

GEMINI_API_KEY = load_api_key()

# Model selection (auto-switches based on TEST_MODE)
GEMINI_MODEL_TEST = "gemini-3-pro-image-preview"  # Full pro model
GEMINI_MODEL_PRODUCTION = "gemini-3-pro-image-preview"  # Best quality

# Technical settings
INPUT_FOLDER = "aquateak_products"
OUTPUT_FOLDER = "generated_images"
FLAT_OUTPUT_FOLDER = "all_generated"
CATEGORY_CONFIG = "category_prompts.json"
LOG_FILE = "generation_log.txt"
REQUEST_DELAY = 0.1  # Minimal delay for maximum speed
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


def call_gemini_api(prompt, input_image_path, api_key, model, aspect_ratio="1:1", image_size="4K"):
    """Call Gemini API to generate styled image with retry logic."""
    import time
    
    max_retries = 3
    base_delay = 10
    
    for attempt in range(max_retries):
        try:
            api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            image_base64 = image_to_base64(input_image_path)
            
            headers = {
                "x-goog-api-key": api_key,
                "Content-Type": "application/json"
            }
            
            # Build image config
            image_config = {"aspectRatio": aspect_ratio}
            if "gemini-3" in model:
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
            if e.response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)
                    tqdm.write(f"    ⏳ Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Rate limit exceeded after {max_retries} attempts.")
            else:
                raise Exception(f"HTTP {e.response.status_code}: {e}")
        except Exception as e:
            raise Exception(f"API call error: {e}")


def get_category_prompt(config, top_cat, mid_cat, granular_cat, shot_type, product_name):
    """Navigate nested config to find category prompt and combine with base prompt.
    White shots (white and white-in-use) use ONLY base prompt, no category context.
    
    IMPORTANT: Product name is ALWAYS included in prompt sent to AI for context.
    This helps AI understand what it's generating (e.g., "Teak Shower Bench").
    However, output filenames use SKU only for cleanliness.
    """
    try:
        base_prompt_key = f"base_prompt_{shot_type}"
        base_prompt = config.get(base_prompt_key, "")
        
        # Always include product name for AI context
        # Example: "Product: Teak Shower Bench. [rest of prompt]"
        prompt_with_product = f"Product: {product_name}. {base_prompt}"
        
        # White shots use ONLY base prompt - no category context to avoid lifestyle bleed
        if shot_type in ['white', 'white-in-use']:
            return prompt_with_product
        
        # Other shot types combine base + category
        cat_prompt = config["categories"][top_cat][mid_cat][granular_cat]["prompt"]
        return f"{prompt_with_product} Setting: {cat_prompt}"
    except KeyError:
        tqdm.write(f"  Warning: Prompt not found for {top_cat}/{mid_cat}/{granular_cat}")
        base_prompt_key = f"base_prompt_{shot_type}"
        base_prompt = config.get(base_prompt_key, "")
        return f"Product: {product_name}. {base_prompt}"


def generate_variants(product_path, prompts_dict, output_subfolder, api_key, model, 
                     variant_counts, aspect_ratio, image_size, 
                     overall_pbar=None, category_pbar=None):
    """Generate AI variants for single product (all 5 shot types).
    
    NEW NAMING CONVENTION:
    - sku - 0 Original.jpg
    - sku - 1 White refresh vX.jpg
    - sku - 1 White in use vX.jpg  
    - sku - 2 Full room vX.jpg
    - sku - 3 Tight vX.jpg
    - sku - 4 Cropped vX.jpg
    """
    import time
    
    successful = 0
    failed = 0
    
    filename = os.path.basename(product_path)
    
    # Extract SKU (everything before first " - ")
    if ' - ' in filename:
        sku = filename.split(' - ')[0]
    else:
        sku = os.path.splitext(filename)[0]
    
    file_ext = os.path.splitext(filename)[1]
    
    # Copy original with new naming: "sku - 0 Original.ext"
    try:
        original_dest = os.path.join(output_subfolder, f"{sku} - 0 Original{file_ext}")
        shutil.copy2(product_path, original_dest)
    except Exception as e:
        log_error(f"Failed to copy original: {e}", f"{sku}: Failed to copy - {e}")
    
    # Shot types with category numbers and display names
    # Format: (internal_type, display_name, category_number, count)
    shot_types = [
        ('white', 'White refresh', '1', variant_counts['white']),
        ('white-in-use', 'White in use', '2', variant_counts['white_in_use']),
        ('room', 'Full room', '3', variant_counts['room']),
        ('tight', 'Tight', '4', variant_counts['tight']),
        ('cropped', 'Cropped', '5', variant_counts['cropped'])
    ]
    
    for internal_type, display_name, cat_num, count in shot_types:
        prompt = prompts_dict[internal_type]
        
        for variant_num in range(1, count + 1):
            max_attempts = 3
            variant_success = False
            
            for attempt in range(1, max_attempts + 1):
                try:
                    generated_image = call_gemini_api(prompt, product_path, api_key, model, aspect_ratio, image_size)
                    
                    if generated_image is None:
                        raise Exception("API returned None")
                    
                    # NEW OUTPUT NAMING: "sku - [cat#] [display name] v[num].jpg"
                    # Example: "624 - 2 Full room v1.jpg"
                    variant_filename = f"{sku} - {cat_num} {display_name} v{variant_num}.jpg"
                    variant_path = os.path.join(output_subfolder, variant_filename)
                    generated_image.save(variant_path, "JPEG", quality=95)
                    
                    successful += 1
                    variant_success = True
                    if overall_pbar:
                        overall_pbar.update(1)
                    if category_pbar:
                        category_pbar.update(1)
                    break
                    
                except Exception as e:
                    if attempt < max_attempts:
                        time.sleep(1)
                        continue
                    else:
                        failed += 1
                        log_error(f"{display_name} v{variant_num} failed: {str(e)[:50]}", 
                                 f"{sku} - v{variant_num} {display_name}: {e}")
                        if overall_pbar:
                            overall_pbar.update(1)
                        if category_pbar:
                            category_pbar.update(1)
            
            if variant_success and not (internal_type == shot_types[-1][0] and variant_num == count):
                time.sleep(REQUEST_DELAY)
    
    return successful, failed


def process_granular_category(category_path, top_cat, mid_cat, granular_cat, config, output_path, api_key, model, 
                              variant_counts, aspect_ratio, image_size, overall_pbar, category_pbar):
    """Process all images in a granular category folder."""
    total_successful = 0
    total_failed = 0
    
    image_files = [f for f in os.listdir(category_path)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not image_files:
        return 0, 0
    
    files_to_process = [image_files[0]] if TEST_MODE else image_files
    
    total_variants = sum(variant_counts.values())
    category_pbar.reset(total=len(files_to_process) * total_variants)
    
    for image_file in files_to_process:
        image_path = os.path.join(category_path, image_file)
        
        # Extract SKU and product name from filename
        # INPUT FORMAT: "624 - Teak Shower Bench.jpg" (from scraper)
        # Extract SKU (everything before first " - ")
        if ' - ' in image_file:
            sku = image_file.split(' - ')[0]
            product_name = ' - '.join(image_file.split(' - ')[1:])
            product_name = os.path.splitext(product_name)[0]  # Remove extension
        else:
            sku = os.path.splitext(image_file)[0]
            product_name = sku  # Fallback if no name
        
        # Create product subfolder using SKU only (no product name in folder structure)
        product_subfolder = os.path.join(output_path, sku)
        os.makedirs(product_subfolder, exist_ok=True)
        
        # Build prompts dict for all 5 shot types
        # CRITICAL: Product name is passed to get_category_prompt()
        # This ensures AI receives context: "Product: Teak Shower Bench. [prompt]"
        prompts_dict = {}
        for shot_type in ['room', 'tight', 'cropped', 'white', 'white-in-use']:
            prompts_dict[shot_type] = get_category_prompt(config, top_cat, mid_cat, granular_cat, shot_type, product_name)
        
        successful, failed = generate_variants(image_path, prompts_dict, product_subfolder, 
                                              api_key, model, variant_counts, 
                                              aspect_ratio, image_size, overall_pbar, category_pbar)
        
        total_successful += successful
        total_failed += failed
    
    return total_successful, total_failed


def count_total_variants():
    """Count total number of variants that will be generated."""
    try:
        config = load_config()
        
        variant_counts = {
            'room': config.get("room_variants_per_image", 3),
            'tight': config.get("tight_variants_per_image", 3),
            'cropped': config.get("cropped_variants_per_image", 2),
            'white': config.get("white_variants_per_image", 1),
            'white_in_use': config.get("white_in_use_variants_per_image", 1)
        }
        
        if TEST_MODE:
            variant_counts = {k: 1 for k in variant_counts.keys()}
        
        total_variants_per_product = sum(variant_counts.values())
        total_variants = 0
        
        for top_name in os.listdir(INPUT_FOLDER):
            top_path = os.path.join(INPUT_FOLDER, top_name)
            if not os.path.isdir(top_path):
                continue
            
            for mid_name in os.listdir(top_path):
                mid_path = os.path.join(top_path, mid_name)
                if not os.path.isdir(mid_path):
                    continue
                
                for granular_name in os.listdir(mid_path):
                    granular_path = os.path.join(mid_path, granular_name)
                    if not os.path.isdir(granular_path):
                        continue
                    
                    image_files = [f for f in os.listdir(granular_path)
                                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                    
                    if image_files:
                        products_count = 1 if TEST_MODE else len(image_files)
                        total_variants += products_count * total_variants_per_product
        
        return total_variants
        
    except Exception as e:
        print(f"Error counting variants: {e}")
        return 0


def flatten_structure():
    """Copy all images from hierarchical structure to single flat folder."""
    print("\n" + "="*60)
    print("Flattening folder structure...")
    print("="*60)
    
    if os.path.exists(FLAT_OUTPUT_FOLDER):
        shutil.rmtree(FLAT_OUTPUT_FOLDER)
    
    os.makedirs(FLAT_OUTPUT_FOLDER, exist_ok=True)
    
    img_extensions = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff")
    seen_names = {}
    total_copied = 0
    
    for root, _, files in os.walk(OUTPUT_FOLDER):
        for filename in files:
            if filename.lower().endswith(img_extensions):
                src_path = os.path.join(root, filename)
                
                name, ext = os.path.splitext(filename)
                count = seen_names.get(filename, 0)
                seen_names[filename] = count + 1
                
                new_name = filename if count == 0 else f"{name}_{count}{ext}"
                dst_path = os.path.join(FLAT_OUTPUT_FOLDER, new_name)
                
                shutil.copy2(src_path, dst_path)
                total_copied += 1
    
    print(f"\n✓ Copied {total_copied} images to {FLAT_OUTPUT_FOLDER}/")


def main():
    """Main generation workflow."""
    print("="*60)
    print("AI Image Generation Pipeline - Step 2")
    print("="*60)
    
    if GEMINI_API_KEY is None:
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
    
    model = GEMINI_MODEL_TEST if TEST_MODE else GEMINI_MODEL_PRODUCTION
    
    try:
        config = load_config()
        
        variant_counts = {
            'room': config.get("room_variants_per_image", 3),
            'tight': config.get("tight_variants_per_image", 3),
            'cropped': config.get("cropped_variants_per_image", 2),
            'white': config.get("white_variants_per_image", 1),
            'white_in_use': config.get("white_in_use_variants_per_image", 1)
        }
        
        aspect_ratio = config.get("aspect_ratio", "1:1")
        image_size = config.get("image_size", "4K")
        
        if TEST_MODE:
            variant_counts = {k: 1 for k in variant_counts.keys()}
        
        total_per_product = sum(variant_counts.values())
        
        print(f"Loaded configuration from {CATEGORY_CONFIG}")
        print(f"Model: {model} ({'TEST' if TEST_MODE else 'PRODUCTION'})")
        print(f"Variants per image:")
        print(f"  Room shots: {variant_counts['room']}")
        print(f"  Tight shots: {variant_counts['tight']}")
        print(f"  Cropped shots: {variant_counts['cropped']}")
        print(f"  White refresh: {variant_counts['white']}")
        print(f"  White in-use: {variant_counts['white_in_use']}")
        print(f"  Total per product: {total_per_product}")
        print(f"Aspect ratio: {aspect_ratio}")
        print(f"\n⚠️ Do not close this window during generation!")
        
        if TEST_MODE:
            print(f"{'!'*60}")
            print("TEST MODE - Processing 1 product per category")
            print(f"1 of each shot type (5 total variants per product)")
            print(f"Estimated cost: ~$36 (150 variants @ $0.24/image at 4K)")
            print(f"{'!'*60}\n")
        
    except Exception as e:
        print(f"\nâœ— ERROR: {e}")
        return
    
    grand_total_successful = 0
    grand_total_failed = 0
    
    print("Counting images to process...")
    total_variants = count_total_variants()
    print(f"Total variants to generate: {total_variants}\n")
    
    overall_pbar = tqdm(total=total_variants, desc="Overall Progress", position=0, leave=True, unit="variant")
    category_pbar = tqdm(total=0, desc="Current Category", position=1, leave=False, unit="variant")
    
    try:
        for top_name in os.listdir(INPUT_FOLDER):
            top_path = os.path.join(INPUT_FOLDER, top_name)
            if not os.path.isdir(top_path):
                continue
            
            tqdm.write(f"\n{'='*60}")
            tqdm.write(f"Processing: {top_name}")
            tqdm.write(f"{'='*60}")
            
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
                    
                    category_pbar.set_description(f"Current: {granular_name[:30]}")
                    
                    successful, failed = process_granular_category(granular_path, top_name, mid_name, granular_name,
                                                                  config, output_path, GEMINI_API_KEY, model, 
                                                                  variant_counts, 
                                                                  aspect_ratio, image_size, 
                                                                  overall_pbar, category_pbar)
                    
                    grand_total_successful += successful
                    grand_total_failed += failed
    
    finally:
        category_pbar.close()
        overall_pbar.close()
    
    # Flatten structure after generation
    flatten_structure()
    
    total_variants = grand_total_successful + grand_total_failed
    success_rate = (grand_total_successful / total_variants * 100) if total_variants > 0 else 0
    
    summary = f"""
{'='*60}
GENERATION COMPLETE
{'='*60}
Successfully generated: {grand_total_successful} / {total_variants} ({success_rate:.1f}%)
Failed: {grand_total_failed}
Hierarchical images: {OUTPUT_FOLDER}/
Flat dump: {FLAT_OUTPUT_FOLDER}/
Error log: {LOG_FILE}

done :)
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