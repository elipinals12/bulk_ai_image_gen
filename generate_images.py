"""
AI Image Generation Pipeline - Step 2
Generates styled lifestyle product images using Gemini Image Generation API.

UPDATED:
- ADDED: Full verification and retry system
- ADDED: Tracks all expected outputs and retries failures
- ADDED: Final verification pass
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

MAX_RETRY_ROUNDS = 3  # How many full retry passes for failed images

log_lock = threading.Lock()

# ============================================================================
# Helper Functions
# ============================================================================

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


def load_config():
    """Load category prompts from JSON."""
    with open(CATEGORY_CONFIG, 'r') as f:
        return json.load(f)


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


def get_category_prompt(config, top_cat, mid_cat, granular_cat, shot_type, product_name, state=None):
    """Navigate nested config to find category prompt and combine with base prompt."""
    base_prompt_key = f"base_prompt_{shot_type}"
    base_prompt = config.get(base_prompt_key, "")
    prompt_with_product = f"Product: {product_name}. {base_prompt}"
    
    if shot_type in ['white', 'white-in-use']:
        if state:
            state_modifier = config.get(f"state_{state}", "")
            if state_modifier:
                return f"{prompt_with_product} STATE: {state_modifier}"
        return prompt_with_product
    
    try:
        cat_prompt = config["categories"][top_cat][mid_cat][granular_cat]["prompt"]
        combined = f"{prompt_with_product} Setting: {cat_prompt}"
    except KeyError:
        combined = prompt_with_product
    
    if state:
        state_modifier = config.get(f"state_{state}", "")
        if state_modifier:
            combined = f"{combined} STATE: {state_modifier}"
    
    return combined


# ============================================================================
# Task Building - Creates manifest of all work to do
# ============================================================================

def build_generation_tasks(config, variant_counts):
    """
    Scan input folder and build complete list of generation tasks.
    Returns list of task dicts with all info needed to generate and verify.
    """
    tasks = []
    
    shot_types = [
        ('white', 'White refresh', '1'),
        ('white-in-use', 'White in use', '2'),
        ('room', 'Full room', '3'),
        ('tight', 'Tight', '4'),
        ('cropped', 'Cropped', '5')
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
                    is_openable = config["categories"][top_name][mid_name][granular_name].get("openable", False)
                except KeyError:
                    is_openable = False
                
                # Get image files
                image_files = [f for f in os.listdir(granular_path)
                               if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                if TEST_MODE:
                    image_files = image_files[:1]
                
                for image_file in image_files:
                    image_path = os.path.join(granular_path, image_file)
                    
                    # Parse SKU and product name
                    if ' - ' in image_file:
                        sku = image_file.split(' - ')[0]
                        product_name = os.path.splitext(' - '.join(image_file.split(' - ')[1:]))[0]
                    else:
                        sku = os.path.splitext(image_file)[0]
                        product_name = sku
                    
                    # Output folder for this product
                    output_subfolder = os.path.join(OUTPUT_FOLDER, top_name, mid_name, granular_name, sku)
                    
                    states = ['closed', 'open'] if is_openable else [None]
                    
                    for state in states:
                        for internal_type, display_name, cat_num in shot_types:
                            count = variant_counts[internal_type.replace('-', '_')]
                            
                            for variant_num in range(1, count + 1):
                                if is_openable:
                                    filename = f"{sku} - {cat_num} {display_name} {state} v{variant_num}.jpg"
                                else:
                                    filename = f"{sku} - {cat_num} {display_name} v{variant_num}.jpg"
                                
                                prompt = get_category_prompt(
                                    config, top_name, mid_name, granular_name,
                                    internal_type, product_name, state
                                )
                                
                                tasks.append({
                                    'source_image': image_path,
                                    'output_folder': output_subfolder,
                                    'output_filename': filename,
                                    'output_path': os.path.join(output_subfolder, filename),
                                    'prompt': prompt,
                                    'sku': sku,
                                    'category': f"{top_name}/{mid_name}/{granular_name}"
                                })
    
    return tasks


# ============================================================================
# Generation with Tracking
# ============================================================================

def generate_single_image(task, api_key, model, aspect_ratio, image_size, 
                          max_retries, base_delay, jpeg_quality):
    """
    Generate a single image. Returns (success, task, error_msg).
    """
    try:
        os.makedirs(task['output_folder'], exist_ok=True)
        
        generated_image = call_gemini_api(
            task['prompt'],
            task['source_image'],
            api_key,
            model,
            aspect_ratio,
            image_size,
            max_retries,
            base_delay
        )
        
        if generated_image is None:
            return (False, task, "API returned None")
        
        generated_image.save(task['output_path'], "JPEG", quality=jpeg_quality)
        
        # Verify file was written
        if not os.path.exists(task['output_path']):
            return (False, task, "File not written")
        
        if os.path.getsize(task['output_path']) < 1000:
            return (False, task, "File too small, likely corrupt")
        
        return (True, task, None)
        
    except Exception as e:
        return (False, task, str(e)[:200])


def run_generation_pass(tasks, api_key, model, aspect_ratio, image_size,
                        max_retries, base_delay, jpeg_quality, max_workers,
                        pass_name="Generation"):
    """
    Run generation for a list of tasks. Returns (successful_tasks, failed_tasks).
    """
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
                    aspect_ratio, image_size, max_retries, base_delay, jpeg_quality
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
    # Group by source image to avoid duplicates
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
    """
    Check which expected outputs exist. Returns (existing, missing).
    """
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
    
    # Check for duplicate filenames
    filenames = [os.path.basename(p) for p in all_images]
    seen = {}
    for f in filenames:
        seen[f] = seen.get(f, 0) + 1
    duplicates = [f for f, count in seen.items() if count > 1]
    
    if duplicates:
        print(f"⚠ WARNING: {len(duplicates)} duplicate filenames!")
        for dup in duplicates[:10]:
            print(f"  - {dup}")
    
    copied = 0
    failed = 0
    
    for src_path in all_images:
        filename = os.path.basename(src_path)
        dst_path = os.path.join(FLAT_OUTPUT_FOLDER, filename)
        
        try:
            shutil.copy2(src_path, dst_path)
            copied += 1
        except Exception as e:
            print(f"  ✗ Failed to copy {filename}: {e}")
            failed += 1
    
    print(f"\n✓ Copied {copied} images to {FLAT_OUTPUT_FOLDER}/")
    if failed:
        print(f"✗ Failed to copy {failed} images")
    
    final_count = len(os.listdir(FLAT_OUTPUT_FOLDER))
    if final_count != len(all_images):
        print(f"⚠ WARNING: Source had {len(all_images)}, destination has {final_count}")
    else:
        print(f"✓ Verified: {final_count} images in flat folder")


# ============================================================================
# Main
# ============================================================================

def main():
    """Main generation workflow with verification and retry."""
    print("="*60)
    print("AI Image Generation Pipeline (with Verification & Retry)")
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
    
    # Load config
    config = load_config()
    
    model = GEMINI_MODEL_TEST if TEST_MODE else GEMINI_MODEL_PRODUCTION
    aspect_ratio = config["aspect_ratio"]
    image_size = config["image_size"]
    max_retries = config["api_retry_max_attempts"]
    base_delay = config["api_retry_base_delay_seconds"]
    jpeg_quality = config["jpeg_quality"]
    max_workers = config.get("max_parallel_requests", 5)
    
    # Build variant counts
    if TEST_MODE:
        test_variants = config["test_mode_variants_per_image"]
        variant_counts = {
            'white': test_variants,
            'white_in_use': test_variants,
            'room': test_variants,
            'tight': test_variants,
            'cropped': test_variants
        }
    else:
        variant_counts = {
            'white': config["white_variants_per_image"],
            'white_in_use': config["white_in_use_variants_per_image"],
            'room': config["room_variants_per_image"],
            'tight': config["tight_variants_per_image"],
            'cropped': config["cropped_variants_per_image"]
        }
    
    print(f"\nMode: {'TEST' if TEST_MODE else 'PRODUCTION'}")
    print(f"Model: {model}")
    print(f"Parallel workers: {max_workers}")
    print(f"Max retry rounds: {MAX_RETRY_ROUNDS}")
    
    # Build complete task manifest
    print("\nBuilding task manifest...")
    all_tasks = build_generation_tasks(config, variant_counts)
    print(f"Total images to generate: {len(all_tasks)}")
    
    # Copy originals
    print("\nCopying original images...")
    copy_original_images(all_tasks)
    
    # Initial generation pass
    successful, failed = run_generation_pass(
        all_tasks, GEMINI_API_KEY, model, aspect_ratio, image_size,
        max_retries, base_delay, jpeg_quality, max_workers,
        pass_name="Initial Generation"
    )
    
    # Retry failed tasks
    retry_round = 1
    while failed and retry_round <= MAX_RETRY_ROUNDS:
        print(f"\n{'='*60}")
        print(f"RETRY ROUND {retry_round}/{MAX_RETRY_ROUNDS} - {len(failed)} images to retry")
        print(f"{'='*60}")
        
        # Small delay before retry
        time.sleep(5)
        
        retry_successful, still_failed = run_generation_pass(
            failed, GEMINI_API_KEY, model, aspect_ratio, image_size,
            max_retries, base_delay, jpeg_quality, max_workers,
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
        print("\nMissing files:")
        for task in missing[:20]:
            print(f"  - {task['output_filename']}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
        
        # Write missing files to log
        log_message("\n=== MISSING FILES ===")
        for task in missing:
            log_message(f"MISSING: {task['output_path']}")
    
    # Flatten
    flatten_structure()
    
    # Summary
    success_rate = (len(verified) / len(all_tasks) * 100) if all_tasks else 0
    
    summary = f"""
{'='*60}
GENERATION COMPLETE
{'='*60}
Total expected:    {len(all_tasks)}
Successfully made: {len(verified)} ({success_rate:.1f}%)
Still missing:     {len(missing)}

Hierarchical: {OUTPUT_FOLDER}/
Flat dump:    {FLAT_OUTPUT_FOLDER}/
Error log:    {LOG_FILE}
{'='*60}
"""
    print(summary)
    log_message(summary)
    
    if missing:
        print("⚠ Some images failed - check generation_log.txt for details")
        return False
    else:
        print("✓ All images generated successfully!")
        return True


if __name__ == "__main__":
    main()