"""
AI Image Generation Pipeline - Step 2
Generates styled lifestyle product images using Gemini Image Generation API.

UPDATED:
- MOVED: All config settings from JSON to this file
- ADDED: "Fitted" white variants with dynamic aspect ratio selection
- ADDED: Analyzes input image to pick best aspect ratio for product
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# ============================================================================
# CONFIGURATION - All settings in one place
# ============================================================================

# --- Mode Settings ---
TEST_MODE = False  # True = 1 variant per type, False = full production!

# --- API Settings ---
GEMINI_MODEL = "gemini-3-pro-image-preview" # Current cutting edge
MAX_PARALLEL_REQUESTS = 10
API_RETRY_MAX_ATTEMPTS = 3
API_RETRY_BASE_DELAY_SECONDS = 10

# --- Output Settings ---
DEFAULT_ASPECT_RATIO = "1:1"  # For all shots except fitted variants
DEFAULT_IMAGE_SIZE = "4K"     # Options: "1K", "2K", "4K" (must be uppercase!)
JPEG_QUALITY = 95             # PIL save quality (0-100, higher = better)

# --- Variant Counts (Production Mode) ---
VARIANTS_PRODUCTION = {
    'white': 1,
    'white_in_use': 2,
    'white_fitted': 1,           # NEW: Fitted aspect ratio white shot
    'white_in_use_fitted': 2,    # NEW: Fitted aspect ratio white-in-use
    'room': 2,
    'tight': 5,
    'cropped': 3,
}

# --- Variant Counts (Test Mode) - All set to 1 ---
VARIANTS_TEST = {k: 1 for k in VARIANTS_PRODUCTION.keys()}

# --- Supported Aspect Ratios (Gemini API) ---
# These are the ONLY valid aspect ratios - API rejects others
SUPPORTED_ASPECT_RATIOS = [
    "1:1",    # Square
    "2:3",    # Portrait
    "3:2",    # Landscape
    "3:4",    # Portrait
    "4:3",    # Landscape  
    "4:5",    # Portrait (Instagram)
    "5:4",    # Landscape
    "9:16",   # Tall portrait (Stories)
    "16:9",   # Widescreen
    "21:9",   # Ultra-wide
]

# --- Retry Settings ---
MAX_RETRY_ROUNDS = 3  # Full retry passes for failed images

# --- Folder Settings ---
INPUT_FOLDER = "aquateak_products"
OUTPUT_FOLDER = "generated_images"
FLAT_OUTPUT_FOLDER = "all_generated"
os.makedirs("logs", exist_ok=True)
LOG_FILE = "logs/generation_log.txt"

# --- Prompt Config Files ---
SHOT_PROMPTS_FILE = "shot_prompts.json"       # Base prompts + state modifiers
CATEGORY_PROMPTS_FILE = "category_prompts.json"  # Category scene descriptions

# ============================================================================
# Thread-safe logging
# ============================================================================

log_lock = threading.Lock()

def log_message(msg, also_print=False):
    """Log message to file (thread-safe)."""
    if also_print:
        tqdm.write(msg)
    with log_lock:
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")
        except:
            pass

# ============================================================================
# API Key Loading
# ============================================================================

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

# ============================================================================
# Aspect Ratio Analysis
# ============================================================================

def get_image_aspect_ratio(image_path):
    """Get the aspect ratio of an image as width/height."""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            return width / height
    except Exception as e:
        log_message(f"Could not read image dimensions: {image_path} - {e}")
        return 1.0  # Default to square

def find_best_aspect_ratio(image_path):
    """
    Analyze input image and find the closest supported Gemini aspect ratio.
    This allows "fitted" shots that match the product's natural proportions.
    """
    actual_ratio = get_image_aspect_ratio(image_path)
    
    # Convert supported ratios to decimal values
    ratio_map = {}
    for ratio_str in SUPPORTED_ASPECT_RATIOS:
        w, h = map(int, ratio_str.split(':'))
        ratio_map[ratio_str] = w / h
    
    # Find closest match
    best_ratio = "1:1"
    best_diff = float('inf')
    
    for ratio_str, ratio_val in ratio_map.items():
        diff = abs(actual_ratio - ratio_val)
        if diff < best_diff:
            best_diff = diff
            best_ratio = ratio_str
    
    return best_ratio

# ============================================================================
# Helper Functions
# ============================================================================

def load_config():
    """Load both prompt config files."""
    with open(SHOT_PROMPTS_FILE, 'r') as f:
        shot_config = json.load(f)
    with open(CATEGORY_PROMPTS_FILE, 'r') as f:
        category_config = json.load(f)
    return shot_config, category_config

def image_to_base64(image_path):
    """Convert image to base64."""
    with open(image_path, 'rb') as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')

def base64_to_image(base64_string):
    """Convert base64 to PIL Image."""
    image_data = base64.b64decode(base64_string)
    return Image.open(BytesIO(image_data))

def call_gemini_api(prompt, input_image_path, api_key, model, aspect_ratio="1:1", 
                   image_size="4K", max_retries=3, base_delay=10):
    """Call Gemini API to generate styled image with retry logic."""
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
            
            response = requests.post(api_endpoint, headers=headers, json=body, timeout=120)
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
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Rate limit exceeded after {max_retries} attempts")
            else:
                raise Exception(f"HTTP {e.response.status_code}: {e}")
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(base_delay)
                continue
            raise

def get_category_prompt(shot_config, category_config, top_cat, mid_cat, granular_cat, shot_type, product_name, state=None):
    """Combine base prompt + category prompt + state modifier into final prompt."""
    # Get base prompt for shot type
    base_prompts = shot_config.get("base_prompts", {})
    base_prompt = base_prompts.get(shot_type, "")
    prompt_with_product = f"Product: {product_name}. {base_prompt}"
    
    # White shots (including fitted) skip category prompts
    if shot_type in ['white', 'white-in-use', 'white-fitted', 'white-in-use-fitted']:
        if state:
            state_modifiers = shot_config.get("state_modifiers", {})
            state_modifier = state_modifiers.get(state, "")
            if state_modifier:
                return f"{prompt_with_product} STATE: {state_modifier}"
        return prompt_with_product
    
    # Add category-specific setting for room/tight/cropped
    try:
        cat_prompt = category_config["categories"][top_cat][mid_cat][granular_cat]["prompt"]
        combined = f"{prompt_with_product} Setting: {cat_prompt}"
    except KeyError:
        combined = prompt_with_product
    
    if state:
        state_modifiers = shot_config.get("state_modifiers", {})
        state_modifier = state_modifiers.get(state, "")
        if state_modifier:
            combined = f"{combined} STATE: {state_modifier}"
    
    return combined

# ============================================================================
# Task Building
# ============================================================================

def build_generation_tasks(shot_config, category_config, variant_counts):
    """
    Scan input folder and build complete list of generation tasks.
    Now includes fitted variants with dynamic aspect ratio.
    """
    tasks = []
    
    # Shot types: (internal_type, display_name, category_number, is_fitted)
    shot_types = [
        ('white', 'White refresh', '1', False),
        ('white-fitted', 'White fitted', '1A', True),
        ('white-in-use', 'White in use', '2', False),
        ('white-in-use-fitted', 'White in use fitted', '2A', True),
        ('room', 'Full room', '3', False),
        ('tight', 'Tight', '4', False),
        ('cropped', 'Cropped', '5', False),
    ]
    
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
                
                # Check if openable
                try:
                    is_openable = category_config["categories"][top_name][mid_name][granular_name].get("openable", False)
                except KeyError:
                    is_openable = False
                
                # Get image files
                image_files = [f for f in os.listdir(granular_path)
                               if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                if TEST_MODE:
                    image_files = image_files[:1]
                
                for image_file in image_files:
                    image_path = os.path.join(granular_path, image_file)
                    
                    # Pre-compute fitted aspect ratio for this image
                    fitted_aspect_ratio = find_best_aspect_ratio(image_path)
                    
                    # Parse SKU and product name
                    if ' - ' in image_file:
                        sku = image_file.split(' - ')[0]
                        product_name = os.path.splitext(' - '.join(image_file.split(' - ')[1:]))[0]
                    else:
                        sku = os.path.splitext(image_file)[0]
                        product_name = sku
                    
                    output_subfolder = os.path.join(OUTPUT_FOLDER, top_name, mid_name, granular_name, sku)
                    states = ['closed', 'open'] if is_openable else [None]
                    
                    for state in states:
                        for internal_type, display_name, cat_num, is_fitted in shot_types:
                            # Get variant count (convert hyphens to underscores for dict key)
                            count_key = internal_type.replace('-', '_')
                            count = variant_counts.get(count_key, 0)
                            
                            if count == 0:
                                continue
                            
                            for variant_num in range(1, count + 1):
                                # Build filename
                                if is_openable:
                                    filename = f"{sku} - {cat_num} {display_name} {state} v{variant_num}.jpg"
                                else:
                                    filename = f"{sku} - {cat_num} {display_name} v{variant_num}.jpg"
                                
                                # Determine aspect ratio
                                if is_fitted:
                                    aspect_ratio = fitted_aspect_ratio
                                else:
                                    aspect_ratio = DEFAULT_ASPECT_RATIO
                                
                                prompt = get_category_prompt(
                                    shot_config, category_config, top_name, mid_name, granular_name,
                                    internal_type, product_name, state
                                )
                                
                                tasks.append({
                                    'source_image': image_path,
                                    'output_folder': output_subfolder,
                                    'output_filename': filename,
                                    'output_path': os.path.join(output_subfolder, filename),
                                    'prompt': prompt,
                                    'aspect_ratio': aspect_ratio,
                                    'sku': sku,
                                    'category': f"{top_name}/{mid_name}/{granular_name}",
                                    'is_fitted': is_fitted,
                                })
    
    return tasks

# ============================================================================
# Generation
# ============================================================================

def generate_single_image(task, api_key, model, image_size, max_retries, base_delay, jpeg_quality):
    """Generate a single image. Returns (success, task, error_msg)."""
    try:
        os.makedirs(task['output_folder'], exist_ok=True)
        
        generated_image = call_gemini_api(
            task['prompt'],
            task['source_image'],
            api_key,
            model,
            task['aspect_ratio'],  # Use task-specific aspect ratio
            image_size,
            max_retries,
            base_delay
        )
        
        if generated_image is None:
            return (False, task, "API returned None")
        
        generated_image.save(task['output_path'], "JPEG", quality=jpeg_quality)
        
        if not os.path.exists(task['output_path']):
            return (False, task, "File not written")
        
        if os.path.getsize(task['output_path']) < 1000:
            return (False, task, "File too small, likely corrupt")
        
        return (True, task, None)
        
    except Exception as e:
        return (False, task, str(e)[:200])

def run_generation_pass(tasks, api_key, model, image_size, max_retries, base_delay, 
                        jpeg_quality, max_workers, pass_name="Generation"):
    """Run generation for a list of tasks. Returns (successful_tasks, failed_tasks)."""
    successful = []
    failed = []
    
    if not tasks:
        return successful, failed
    
    print(f"\n{pass_name}: {len(tasks)} images with {max_workers} workers")
    
    with tqdm(total=len(tasks), desc=pass_name, unit="img") as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    generate_single_image, task, api_key, model,
                    image_size, max_retries, base_delay, jpeg_quality
                ): task for task in tasks
            }
            
            for future in as_completed(futures):
                success, task, error = future.result()
                
                if success:
                    successful.append(task)
                else:
                    failed.append(task)
                    log_message(f"FAILED: {task['output_filename']} - {error}")
                
                pbar.update(1)
                pbar.set_postfix(ok=len(successful), fail=len(failed))
    
    return successful, failed

def copy_original_images(tasks):
    """Copy original source images to output folders."""
    seen_sources = set()
    
    for task in tasks:
        source = task['source_image']
        if source in seen_sources:
            continue
        seen_sources.add(source)
        
        filename = os.path.basename(source)
        if ' - ' in filename:
            sku = filename.split(' - ')[0]
        else:
            sku = os.path.splitext(filename)[0]
        
        ext = os.path.splitext(filename)[1]
        original_dest = os.path.join(task['output_folder'], f"{sku} - 0 Original{ext}")
        
        try:
            os.makedirs(task['output_folder'], exist_ok=True)
            shutil.copy2(source, original_dest)
        except Exception as e:
            log_message(f"Failed to copy original {source}: {e}", also_print=True)

def verify_all_outputs(tasks):
    """Check which expected outputs exist. Returns (existing, missing)."""
    existing = []
    missing = []
    
    for task in tasks:
        if os.path.exists(task['output_path']) and os.path.getsize(task['output_path']) > 1000:
            existing.append(task)
        else:
            missing.append(task)
    
    return existing, missing

def flatten_structure():
    """Copy all images from hierarchical structure to single flat folder."""
    print("\n" + "="*60)
    print("Flattening folder structure...")
    print("="*60)
    
    if os.path.exists(FLAT_OUTPUT_FOLDER):
        shutil.rmtree(FLAT_OUTPUT_FOLDER)
    os.makedirs(FLAT_OUTPUT_FOLDER, exist_ok=True)
    
    img_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
    all_images = []
    
    for root, _, files in os.walk(OUTPUT_FOLDER):
        for filename in files:
            if os.path.splitext(filename)[1].lower() in img_extensions:
                all_images.append(os.path.join(root, filename))
    
    print(f"Found {len(all_images)} images to flatten")
    
    copied = 0
    for src_path in all_images:
        filename = os.path.basename(src_path)
        dst_path = os.path.join(FLAT_OUTPUT_FOLDER, filename)
        try:
            shutil.copy2(src_path, dst_path)
            copied += 1
        except Exception as e:
            print(f"  ✗ Failed to copy {filename}: {e}")
    
    print(f"\n✓ Copied {copied} images to {FLAT_OUTPUT_FOLDER}/")

# ============================================================================
# Main
# ============================================================================

def main():
    """Main generation workflow with verification and retry."""
    print("="*60)
    print("AI Image Generation Pipeline")
    print("="*60)
    
    if GEMINI_API_KEY is None:
        return
    
    if not os.path.exists(INPUT_FOLDER):
        print(f"\n✗ ERROR: Input folder '{INPUT_FOLDER}' not found")
        return
    
    # Clear log
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    # Clear output
    if os.path.exists(OUTPUT_FOLDER):
        print(f"\nDeleting existing folder: {OUTPUT_FOLDER}/")
        shutil.rmtree(OUTPUT_FOLDER)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    # Load config files
    shot_config, category_config = load_config()
    
    # Select variant counts based on mode
    variant_counts = VARIANTS_TEST if TEST_MODE else VARIANTS_PRODUCTION
    
    print(f"\nMode: {'TEST' if TEST_MODE else 'PRODUCTION'}")
    print(f"Model: {GEMINI_MODEL}")
    print(f"Image Size: {DEFAULT_IMAGE_SIZE}")
    print(f"Default Aspect Ratio: {DEFAULT_ASPECT_RATIO}")
    print(f"Parallel workers: {MAX_PARALLEL_REQUESTS}")
    print(f"Max retry rounds: {MAX_RETRY_ROUNDS}")
    print(f"\nVariant counts:")
    for k, v in variant_counts.items():
        print(f"  {k}: {v}")
    
    # Build task manifest
    print("\nBuilding task manifest...")
    all_tasks = build_generation_tasks(shot_config, category_config, variant_counts)
    
    # Count fitted vs standard
    fitted_count = sum(1 for t in all_tasks if t.get('is_fitted'))
    standard_count = len(all_tasks) - fitted_count
    print(f"Total images to generate: {len(all_tasks)}")
    print(f"  Standard (1:1): {standard_count}")
    print(f"  Fitted (dynamic AR): {fitted_count}")
    
    # Copy originals
    print("\nCopying original images...")
    copy_original_images(all_tasks)
    
    # Initial generation
    successful, failed = run_generation_pass(
        all_tasks, GEMINI_API_KEY, GEMINI_MODEL, DEFAULT_IMAGE_SIZE,
        API_RETRY_MAX_ATTEMPTS, API_RETRY_BASE_DELAY_SECONDS, 
        JPEG_QUALITY, MAX_PARALLEL_REQUESTS,
        pass_name="Initial Generation"
    )
    
    # Retry failed
    retry_round = 1
    while failed and retry_round <= MAX_RETRY_ROUNDS:
        print(f"\n{'='*60}")
        print(f"RETRY ROUND {retry_round}/{MAX_RETRY_ROUNDS} - {len(failed)} images")
        print(f"{'='*60}")
        time.sleep(5)
        
        retry_successful, still_failed = run_generation_pass(
            failed, GEMINI_API_KEY, GEMINI_MODEL, DEFAULT_IMAGE_SIZE,
            API_RETRY_MAX_ATTEMPTS, API_RETRY_BASE_DELAY_SECONDS,
            JPEG_QUALITY, MAX_PARALLEL_REQUESTS,
            pass_name=f"Retry Round {retry_round}"
        )
        
        successful.extend(retry_successful)
        failed = still_failed
        retry_round += 1
    
    # Final verification
    print("\n" + "="*60)
    print("FINAL VERIFICATION")
    print("="*60)
    
    verified, missing = verify_all_outputs(all_tasks)
    print(f"Expected: {len(all_tasks)}")
    print(f"Verified: {len(verified)}")
    print(f"Missing:  {len(missing)}")
    
    if missing:
        print("\nMissing files (first 20):")
        for task in missing[:20]:
            print(f"  - {task['output_filename']}")
    
    # Flatten
    flatten_structure()
    
    # Summary
    success_rate = (len(verified) / len(all_tasks) * 100) if all_tasks else 0
    print(f"\n{'='*60}")
    print("GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total expected:    {len(all_tasks)}")
    print(f"Successfully made: {len(verified)} ({success_rate:.1f}%)")
    print(f"Still missing:     {len(missing)}")
    print(f"\nHierarchical: {OUTPUT_FOLDER}/")
    print(f"Flat dump:    {FLAT_OUTPUT_FOLDER}/")
    print(f"Error log:    {LOG_FILE}")
    
    return len(missing) == 0

if __name__ == "__main__":
    main()