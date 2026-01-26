"""
AI Image Generation Pipeline - Step 2
Generates styled lifestyle product images using Gemini Image Generation API.
Traverses hierarchical category structure and applies appropriate prompts.
Generates 5 shot types: room, tight, cropped, white, white-in-use.

UPDATED:
- FIXED: REQUEST_DELAY variable reference bug
- ADDED: Parallel processing with ThreadPoolExecutor
- ADDED: Configurable max_workers in JSON config
- Open/closed variants for openable products (cabinets, hampers, storage)
- Auto-detects openable flag per category
- Doubles all variants for openable products
- New naming: includes "open" or "closed" suffix
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

# ============================================================================
# Configuration
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

GEMINI_MODEL_TEST = "gemini-3-pro-image-preview"
GEMINI_MODEL_PRODUCTION = "gemini-3-pro-image-preview"

INPUT_FOLDER = "aquateak_products"
OUTPUT_FOLDER = "generated_images"
FLAT_OUTPUT_FOLDER = "all_generated"
CATEGORY_CONFIG = "category_prompts.json"
LOG_FILE = "generation_log.txt"
TEST_MODE = True

# Thread-safe logging
log_lock = threading.Lock()

# ============================================================================
# Helper Functions
# ============================================================================

def log_error(console_msg, log_msg):
    """Log error to console and file (thread-safe)."""
    tqdm.write(f"  ✗ {console_msg}")
    with log_lock:
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


def call_gemini_api(prompt, input_image_path, api_key, model, aspect_ratio="1:1", image_size="4K", 
                   max_retries=3, base_delay=10):
    """Call Gemini API to generate styled image with retry logic."""
    import time
    
    for attempt in range(max_retries):
        try:
            api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            image_base64 = image_to_base64(input_image_path)
            
            headers = {
                "x-goog-api-key": api_key,
                "Content-Type": "application/json"
            }
            
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
                    tqdm.write(f"    ⏳ Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Rate limit exceeded after {max_retries} attempts.")
            else:
                raise Exception(f"HTTP {e.response.status_code}: {e}")
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(base_delay)
                continue
            raise Exception(f"API call error: {e}")


def get_category_prompt(config, top_cat, mid_cat, granular_cat, shot_type, product_name, state=None):
    """Navigate nested config to find category prompt and combine with base prompt."""
    try:
        base_prompt_key = f"base_prompt_{shot_type}"
        base_prompt = config.get(base_prompt_key, "")
        
        prompt_with_product = f"Product: {product_name}. {base_prompt}"
        
        if shot_type in ['white', 'white-in-use']:
            if state:
                state_key = f"state_{state}"
                state_modifier = config.get(state_key, "")
                if state_modifier:
                    return f"{prompt_with_product} STATE: {state_modifier}"
            return prompt_with_product
        
        cat_prompt = config["categories"][top_cat][mid_cat][granular_cat]["prompt"]
        combined = f"{prompt_with_product} Setting: {cat_prompt}"
        
        if state:
            state_key = f"state_{state}"
            state_modifier = config.get(state_key, "")
            if state_modifier:
                combined = f"{combined} STATE: {state_modifier}"
        
        return combined
        
    except KeyError:
        tqdm.write(f"  Warning: Prompt not found for {top_cat}/{mid_cat}/{granular_cat}")
        base_prompt_key = f"base_prompt_{shot_type}"
        base_prompt = config.get(base_prompt_key, "")
        return f"Product: {product_name}. {base_prompt}"


def generate_single_variant(args):
    """Generate a single variant - designed for parallel execution.
    
    Returns tuple: (success: bool, variant_info: str)
    """
    (product_path, prompt, output_path, variant_filename, api_key, model,
     aspect_ratio, image_size, max_retries, base_delay, jpeg_quality) = args
    
    max_attempts = 3
    
    for attempt in range(1, max_attempts + 1):
        try:
            generated_image = call_gemini_api(
                prompt, product_path, api_key, model,
                aspect_ratio, image_size, max_retries, base_delay
            )
            
            if generated_image is None:
                raise Exception("API returned None")
            
            variant_path = os.path.join(output_path, variant_filename)
            generated_image.save(variant_path, "JPEG", quality=jpeg_quality)
            
            return (True, variant_filename)
            
        except Exception as e:
            if attempt < max_attempts:
                import time
                time.sleep(1)
                continue
            else:
                return (False, f"{variant_filename}: {str(e)[:100]}")
    
    return (False, f"{variant_filename}: Unknown error")


def generate_variants_parallel(product_path, prompts_dict, output_subfolder, api_key, model, 
                               variant_counts, aspect_ratio, image_size, is_openable,
                               max_retries, base_delay, jpeg_quality, max_workers,
                               overall_pbar=None, category_pbar=None):
    """Generate AI variants for single product using parallel execution."""
    
    successful = 0
    failed = 0
    
    filename = os.path.basename(product_path)
    
    if ' - ' in filename:
        sku = filename.split(' - ')[0]
    else:
        sku = os.path.splitext(filename)[0]
    
    file_ext = os.path.splitext(filename)[1]
    
    # Copy original
    try:
        original_dest = os.path.join(output_subfolder, f"{sku} - 0 Original{file_ext}")
        shutil.copy2(product_path, original_dest)
    except Exception as e:
        log_error(f"Failed to copy original: {e}", f"{sku}: Failed to copy - {e}")
    
    # Shot types configuration
    shot_types = [
        ('white', 'White refresh', '1', variant_counts['white']),
        ('white-in-use', 'White in use', '2', variant_counts['white_in_use']),
        ('room', 'Full room', '3', variant_counts['room']),
        ('tight', 'Tight', '4', variant_counts['tight']),
        ('cropped', 'Cropped', '5', variant_counts['cropped'])
    ]
    
    states = ['closed', 'open'] if is_openable else [None]
    
    # Build list of all variant tasks
    tasks = []
    for state in states:
        for internal_type, display_name, cat_num, count in shot_types:
            prompt = prompts_dict[internal_type][state] if is_openable else prompts_dict[internal_type]
            
            for variant_num in range(1, count + 1):
                if is_openable:
                    variant_filename = f"{sku} - {cat_num} {display_name} {state} v{variant_num}.jpg"
                else:
                    variant_filename = f"{sku} - {cat_num} {display_name} v{variant_num}.jpg"
                
                tasks.append((
                    product_path, prompt, output_subfolder, variant_filename,
                    api_key, model, aspect_ratio, image_size,
                    max_retries, base_delay, jpeg_quality
                ))
    
    # Execute tasks in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(generate_single_variant, task): task[3] for task in tasks}
        
        for future in as_completed(futures):
            variant_name = futures[future]
            try:
                success, info = future.result()
                if success:
                    successful += 1
                else:
                    failed += 1
                    log_error(f"Failed: {info[:50]}", f"{sku}: {info}")
            except Exception as e:
                failed += 1
                log_error(f"Exception: {variant_name}", f"{sku} - {variant_name}: {e}")
            
            if overall_pbar:
                overall_pbar.update(1)
            if category_pbar:
                category_pbar.update(1)
    
    return successful, failed


def process_granular_category(category_path, top_cat, mid_cat, granular_cat, config, output_path, 
                              api_key, model, variant_counts, aspect_ratio, image_size, 
                              max_retries, base_delay, jpeg_quality, max_workers,
                              overall_pbar, category_pbar):
    """Process all images in a granular category folder."""
    total_successful = 0
    total_failed = 0
    
    image_files = [f for f in os.listdir(category_path)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not image_files:
        return 0, 0
    
    files_to_process = [image_files[0]] if TEST_MODE else image_files
    
    try:
        is_openable = config["categories"][top_cat][mid_cat][granular_cat].get("openable", False)
    except KeyError:
        is_openable = False
    
    total_variants_per_product = sum(variant_counts.values())
    if is_openable:
        total_variants_per_product *= 2
    
    category_pbar.reset(total=len(files_to_process) * total_variants_per_product)
    
    for image_file in files_to_process:
        image_path = os.path.join(category_path, image_file)
        
        if ' - ' in image_file:
            sku = image_file.split(' - ')[0]
            product_name = ' - '.join(image_file.split(' - ')[1:])
            product_name = os.path.splitext(product_name)[0]
        else:
            sku = os.path.splitext(image_file)[0]
            product_name = sku
        
        product_subfolder = os.path.join(output_path, sku)
        os.makedirs(product_subfolder, exist_ok=True)
        
        if is_openable:
            prompts_dict = {}
            for shot_type in ['room', 'tight', 'cropped', 'white', 'white-in-use']:
                prompts_dict[shot_type] = {
                    'closed': get_category_prompt(config, top_cat, mid_cat, granular_cat, shot_type, product_name, 'closed'),
                    'open': get_category_prompt(config, top_cat, mid_cat, granular_cat, shot_type, product_name, 'open')
                }
        else:
            prompts_dict = {}
            for shot_type in ['room', 'tight', 'cropped', 'white', 'white-in-use']:
                prompts_dict[shot_type] = get_category_prompt(config, top_cat, mid_cat, granular_cat, shot_type, product_name)
        
        successful, failed = generate_variants_parallel(
            image_path, prompts_dict, product_subfolder, 
            api_key, model, variant_counts, 
            aspect_ratio, image_size, is_openable,
            max_retries, base_delay, jpeg_quality, max_workers,
            overall_pbar, category_pbar
        )
        
        total_successful += successful
        total_failed += failed
    
    return total_successful, total_failed


def count_total_variants():
    """Count total number of variants that will be generated."""
    try:
        config = load_config()
        
        variant_counts = {
            'room': config["room_variants_per_image"],
            'tight': config["tight_variants_per_image"],
            'cropped': config["cropped_variants_per_image"],
            'white': config["white_variants_per_image"],
            'white_in_use': config["white_in_use_variants_per_image"]
        }
        
        if TEST_MODE:
            test_mode_variants = config["test_mode_variants_per_image"]
            variant_counts = {k: test_mode_variants for k in variant_counts.keys()}
        
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
                    
                    try:
                        is_openable = config["categories"][top_name][mid_name][granular_name].get("openable", False)
                    except KeyError:
                        is_openable = False
                    
                    image_files = [f for f in os.listdir(granular_path)
                                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                    
                    if image_files:
                        products_count = 1 if TEST_MODE else len(image_files)
                        variants = total_variants_per_product * 2 if is_openable else total_variants_per_product
                        total_variants += products_count * variants
        
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
    
    print(f"\n✔ Copied {total_copied} images to {FLAT_OUTPUT_FOLDER}/")


def main():
    """Main generation workflow."""
    print("="*60)
    print("AI Image Generation Pipeline - Step 2 (PARALLEL)")
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
            'room': config["room_variants_per_image"],
            'tight': config["tight_variants_per_image"],
            'cropped': config["cropped_variants_per_image"],
            'white': config["white_variants_per_image"],
            'white_in_use': config["white_in_use_variants_per_image"]
        }
        
        aspect_ratio = config["aspect_ratio"]
        image_size = config["image_size"]
        max_retries = config["api_retry_max_attempts"]
        base_delay = config["api_retry_base_delay_seconds"]
        jpeg_quality = config["jpeg_quality"]
        test_mode_variants = config["test_mode_variants_per_image"]
        
        # NEW: Configurable parallelism (default 5 if not in config)
        max_workers = config.get("max_parallel_requests", 5)
        
        if TEST_MODE:
            variant_counts = {k: test_mode_variants for k in variant_counts.keys()}
        
        total_per_product = sum(variant_counts.values())
        
        print(f"Loaded configuration from {CATEGORY_CONFIG}")
        print(f"Model: {model}")
        print(f"Mode: {'TEST' if TEST_MODE else 'PRODUCTION'}")
        print(f"Resolution: {image_size} ({aspect_ratio})")
        print(f"JPEG Quality: {jpeg_quality}")
        print(f"Parallel requests: {max_workers} concurrent")
        print(f"API Retry: {max_retries} attempts, {base_delay}s base delay")
        print(f"Variants per image:")
        print(f"  Room shots: {variant_counts['room']}")
        print(f"  Tight shots: {variant_counts['tight']}")
        print(f"  Cropped shots: {variant_counts['cropped']}")
        print(f"  White refresh: {variant_counts['white']}")
        print(f"  White in-use: {variant_counts['white_in_use']}")
        print(f"  Total per product: {total_per_product}")
        if TEST_MODE:
            print(f"  (Test mode: {test_mode_variants} variant per type)")
        print(f"  (Doubled for openable products)")
        print(f"\n⚠️ Do not close this window during generation!")
        
        if TEST_MODE:
            print(f"{'!'*60}")
            print("TEST MODE - Processing 1 product per category")
            print(f"Running {max_workers} parallel requests for speed")
            print(f"{'!'*60}\n")
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
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
                    
                    successful, failed = process_granular_category(
                        granular_path, top_name, mid_name, granular_name,
                        config, output_path, GEMINI_API_KEY, model, 
                        variant_counts, aspect_ratio, image_size,
                        max_retries, base_delay, jpeg_quality, max_workers,
                        overall_pbar, category_pbar
                    )
                    
                    grand_total_successful += successful
                    grand_total_failed += failed
    
    finally:
        category_pbar.close()
        overall_pbar.close()
    
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