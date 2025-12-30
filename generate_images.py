"""
AI Image Generation Pipeline - Step 2

Generates styled lifestyle product images using Gemini Image Generation API.
Removes watermarks using reverse alpha blending for pixel-perfect restoration.

Test mode: Processes 3 images (one per category) with fast model (~$0.36)
Production mode: Processes all images with Pro model (~$0.40 per product)

See README.md for complete documentation.
"""

import os
import json
import base64
import shutil
import requests
import numpy as np
from pathlib import Path
from PIL import Image
from io import BytesIO
from tqdm import tqdm

# ============================================================================
# Configuration
# ============================================================================

# Gemini API Settings
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"  # Get from: https://aistudio.google.com/apikey
GEMINI_MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro (highest quality)
API_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Directory Paths
INPUT_FOLDER = "aquateak_products"      # Input: scraped product images organized by category
OUTPUT_FOLDER = "generated_images"      # Output: AI-generated variants organized by product
CATEGORY_CONFIG = "category_prompts.json"  # Category-specific prompts and settings
LOG_FILE = "generation_log.txt"         # Error log for failed generations

# Generation Parameters
VARIANTS_PER_IMAGE = 3   # Number of AI variants to generate per product image
REQUEST_DELAY = 1.0      # Delay between API calls (seconds) to avoid rate limiting
TEST_MODE = False        # If True, only process first image found (for testing)

# Reverse Alpha Blending - Watermark Removal
# Alpha maps contain pre-captured watermark transparency values for mathematical restoration
ALPHA_MAP_48 = "bg_48.png"  # Alpha map for small watermarks (images ≤1024px)
ALPHA_MAP_96 = "bg_96.png"  # Alpha map for large watermarks (images >1024px)

# ============================================================================
# Helper Functions
# ============================================================================

def log_error(console_msg, log_msg):
    """Log error to console and append to log file."""
    tqdm.write(f"  ❌ {console_msg}")
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{log_msg}\n")
    except Exception as e:
        tqdm.write(f"  Warning: Couldn't write to log file: {e}")


def load_config():
    """Load category prompts and generation settings from JSON config."""
    try:
        with open(CATEGORY_CONFIG, 'r') as f:
            config = json.load(f)
            return config
    except Exception as e:
        print(f"Error loading config from {CATEGORY_CONFIG}: {e}")
        raise


def image_to_base64(image_path):
    """Convert image file to base64 string for API transmission."""
    try:
        with open(image_path, 'rb') as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        raise Exception(f"Error converting image to base64: {e}")


def base64_to_image(base64_string):
    """Convert base64 string to PIL Image."""
    try:
        image_data = base64.b64decode(base64_string)
        return Image.open(BytesIO(image_data))
    except Exception as e:
        raise Exception(f"Error converting base64 to image: {e}")


def get_watermark_dimensions(image_width, image_height):
    """
    Determine watermark size and margin based on image dimensions.
    Returns: (watermark_size, margin) in pixels
    """
    if image_width <= 1024 or image_height <= 1024:
        return 48, 32  # Small watermark
    else:
        return 96, 64  # Large watermark


def remove_watermark(image):
    """
    Remove Gemini watermark using reverse alpha blending.
    
    Process:
    1. Determine watermark size based on image dimensions
    2. Load corresponding alpha map (transparency values)
    3. Extract watermarked region (bottom-right corner)
    4. Apply reverse alpha formula: original = watermarked / (1 - alpha)
    5. Replace watermarked region with restored pixels
    
    Returns: PIL Image with watermark removed (or original if removal fails)
    """
    try:
        width, height = image.size
        wm_size, margin = get_watermark_dimensions(width, height)
        
        # Select appropriate alpha map
        alpha_map_file = ALPHA_MAP_48 if wm_size == 48 else ALPHA_MAP_96
        
        if not os.path.exists(alpha_map_file):
            tqdm.write(f"  Warning: Alpha map '{alpha_map_file}' not found, skipping watermark removal")
            return image
        
        # Load alpha map and extract transparency channel
        alpha_img = Image.open(alpha_map_file).convert('RGB')
        alpha_array = np.array(alpha_img).astype(np.float32)
        alpha_map = np.max(alpha_array, axis=2) / 255.0  # Max RGB = transparency
        
        # Convert image to float32 for precise calculations
        img_array = np.array(image.convert('RGB')).astype(np.float32)
        
        # Calculate watermark region coordinates (bottom-right)
        x1 = width - wm_size - margin
        y1 = height - wm_size - margin
        x2 = width - margin
        y2 = height - margin
        
        watermarked_region = img_array[y1:y2, x1:x2, :]
        
        # Expand alpha map to RGB channels
        alpha_expanded = alpha_map[:, :, np.newaxis]
        
        # Prevent division by zero
        epsilon = 1e-6
        safe_alpha = np.clip(alpha_expanded, epsilon, 1.0 - epsilon)
        
        # Reverse alpha blending: original = watermarked / (1 - alpha)
        restored_region = watermarked_region / (1.0 - safe_alpha)
        restored_region = np.clip(restored_region, 0, 255)
        
        # Replace watermarked region
        result_array = img_array.copy()
        result_array[y1:y2, x1:x2, :] = restored_region
        
        # Convert back to PIL Image
        result_img = Image.fromarray(result_array.astype(np.uint8))
        return result_img
        
    except Exception as e:
        tqdm.write(f"  Warning: Watermark removal failed: {e}")
        return image


def call_gemini_api(prompt, input_image_path, aspect_ratio="1:1", output_mime_type="image/jpeg"):
    """
    Call Gemini API to generate styled product image.
    Sends combined prompt + original image, returns AI-generated variant.
    """
    try:
        # Encode input image as base64
        image_base64 = image_to_base64(input_image_path)
        
        # Prepare API request
        headers = {
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Build request payload (prompt + reference image)
        body = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
            }
        }
        
        # Add aspect ratio if specified
        if aspect_ratio:
            body["generationConfig"]["imageConfig"] = {
                "aspectRatio": aspect_ratio
            }
        
        # Make API request
        response = requests.post(
            API_ENDPOINT,
            headers=headers,
            json=body,
            timeout=60
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Extract image from response
        if "candidates" in result and len(result["candidates"]) > 0:
            parts = result["candidates"][0].get("content", {}).get("parts", [])
            
            for part in parts:
                if "inlineData" in part:
                    image_data = part["inlineData"].get("data")
                    if image_data:
                        return base64_to_image(image_data)
        
        raise Exception("No image data in API response")
        
    except requests.exceptions.Timeout:
        raise Exception("API request timed out")
    except requests.exceptions.RequestException as e:
        raise Exception(f"API request failed: {e}")
    except Exception as e:
        raise Exception(f"API call error: {e}")


def generate_variants(product_path, category_name, config, output_subfolder):
    """
    Generate AI-styled variants for a single product image.
    Copies original as v0, generates N variants via API, removes watermarks, saves as v1-vN.
    Returns: (successful_count, failed_count)
    """
    successful = 0
    failed = 0
    
    filename = os.path.basename(product_path)
    name_without_ext = os.path.splitext(filename)[0]
    file_ext = os.path.splitext(filename)[1]
    
    # Extract SKU from filename (format: "SKU - Product Name.ext")
    sku = name_without_ext.split(' - ')[0] if ' - ' in name_without_ext else 'UNKNOWN'
    
    # Copy original as v0
    try:
        original_dest = os.path.join(output_subfolder, f"v0 {name_without_ext}{file_ext}")
        shutil.copy2(product_path, original_dest)
    except Exception as e:
        log_error(
            f"Failed to copy original: {e}",
            f"{sku} - {name_without_ext}: Failed to copy original - {e}"
        )
    
    # Build combined prompt
    base_prompt = config.get("base_prompt", "")
    category_prompt = config["categories"][category_name]["prompt"]
    combined_prompt = f"{base_prompt} {category_prompt}"
    
    # Get API settings from config
    gen_settings = config.get("generation_settings", {})
    aspect_ratio = gen_settings.get("aspect_ratio", "1:1")
    output_mime = gen_settings.get("output_mime_type", "image/jpeg")
    
    # Generate variants
    for variant_num in range(1, VARIANTS_PER_IMAGE + 1):
        try:
            # Call Gemini API
            generated_image = call_gemini_api(
                combined_prompt,
                product_path,
                aspect_ratio,
                output_mime
            )
            
            if generated_image is None:
                raise Exception("API returned None")
            
            # Remove watermark
            cleaned_image = remove_watermark(generated_image)
            
            # Save variant
            variant_filename = f"v{variant_num} {name_without_ext}.jpg"
            variant_path = os.path.join(output_subfolder, variant_filename)
            cleaned_image.save(variant_path, "JPEG", quality=95)
            
            successful += 1
            tqdm.write(f"    ✓ Generated v{variant_num}")
            
            # Delay between API calls
            if variant_num < VARIANTS_PER_IMAGE:
                import time
                time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            failed += 1
            log_error(
                f"Variant v{variant_num} failed: {str(e)[:50]}",
                f"{sku} - {name_without_ext} - v{variant_num}: {e}"
            )
    
    return successful, failed


def process_category(category_name, category_path, config, output_category_path):
    """
    Process all images in a category (or just first image in test mode).
    Returns: (total_successful_variants, total_failed_variants)
    """
    total_successful = 0
    total_failed = 0
    
    # Get all image files in category
    image_files = [
        f for f in os.listdir(category_path)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]
    
    if not image_files:
        return 0, 0
    
    # Process each image
    for image_file in tqdm(image_files, desc=f"  {category_name}", leave=False, unit="img"):
        image_path = os.path.join(category_path, image_file)
        name_without_ext = os.path.splitext(image_file)[0]
        
        # Create product subfolder
        product_subfolder = os.path.join(output_category_path, name_without_ext)
        os.makedirs(product_subfolder, exist_ok=True)
        
        # Generate variants
        successful, failed = generate_variants(
            image_path,
            category_name,
            config,
            product_subfolder
        )
        
        total_successful += successful
        total_failed += failed
        
        # Exit after first image in test mode
        if TEST_MODE:
            break
    
    return total_successful, total_failed


def main():
    """Main generation workflow. See README.md for details."""
    print("="*60)
    print("AI Image Generation Pipeline - Step 2")
    print("="*60)
    
    # Validate API key
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("\n❌ ERROR: Please set your GEMINI_API_KEY in the script")
        return
    
    # Check input folder exists
    if not os.path.exists(INPUT_FOLDER):
        print(f"\n❌ ERROR: Input folder '{INPUT_FOLDER}' not found")
        print("Run scraper.py first to create product images")
        return
    
    # Delete existing log file
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    # Delete and recreate output folder
    if os.path.exists(OUTPUT_FOLDER):
        print(f"\nDeleting existing folder: {OUTPUT_FOLDER}/")
        shutil.rmtree(OUTPUT_FOLDER)
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    print(f"Created fresh output folder: {OUTPUT_FOLDER}/\n")
    
    # Load configuration
    try:
        config = load_config()
        print(f"Loaded configuration from {CATEGORY_CONFIG}")
        print(f"Model: {GEMINI_MODEL} ({'TEST' if TEST_MODE else 'PRODUCTION'})")
        print(f"Variants per image: {VARIANTS_PER_IMAGE}")
        print(f"Watermark removal: Reverse Alpha Blending")
        
        if TEST_MODE:
            print(f"\n{'!'*60}")
            print("TEST MODE ACTIVE")
            print(f"- Will process 3 images (one from each of 3 categories)")
            print(f"- Using fast model: {GEMINI_MODEL}")
            print(f"- Cost: ~$0.36 total (9 variants)")
            print(f"{'!'*60}")
        else:
            print(f"\nProduction mode - Processing all images with {GEMINI_MODEL}")
        
        # Check for alpha maps
        missing_maps = []
        if not os.path.exists(ALPHA_MAP_48):
            missing_maps.append(ALPHA_MAP_48)
        if not os.path.exists(ALPHA_MAP_96):
            missing_maps.append(ALPHA_MAP_96)
        
        if missing_maps:
            print(f"\n⚠️  WARNING: Missing alpha map files: {', '.join(missing_maps)}")
            print("Watermark removal will be skipped for affected images.")
        
        print()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return
    
    # Get list of category folders
    categories = [
        d for d in os.listdir(INPUT_FOLDER)
        if os.path.isdir(os.path.join(INPUT_FOLDER, d))
    ]
    
    if not categories:
        print(f"❌ ERROR: No category folders found in {INPUT_FOLDER}/")
        return
    
    print(f"Found {len(categories)} categories to process\n")
    
    # Process categories
    grand_total_successful = 0
    grand_total_failed = 0
    categories_processed = 0  # Track for test mode
    
    for category in tqdm(categories, desc="Categories", unit="cat"):
        category_input_path = os.path.join(INPUT_FOLDER, category)
        category_output_path = os.path.join(OUTPUT_FOLDER, category)
        
        os.makedirs(category_output_path, exist_ok=True)
        
        # Skip if category not in config
        if category not in config["categories"]:
            tqdm.write(f"  ⚠️  Category '{category}' not in config, skipping")
            continue
        
        # Process all images in category
        successful, failed = process_category(
            category,
            category_input_path,
            config,
            category_output_path
        )
        
        grand_total_successful += successful
        grand_total_failed += failed
        
        # Track categories processed (only count if we processed at least one image)
        if successful > 0 or failed > 0:
            categories_processed += 1
        
        # Exit after 3 categories in test mode
        if TEST_MODE and categories_processed >= 3:
            tqdm.write(f"\n✓ Test mode complete - processed 3 images from {categories_processed} categories")
            break
    
    # Summary statistics
    total_variants = grand_total_successful + grand_total_failed
    success_rate = (grand_total_successful / total_variants * 100) if total_variants > 0 else 0
    
    # Display summary
    summary = f"""
{'='*60}
GENERATION COMPLETE
{'='*60}
Successfully generated: {grand_total_successful} / {total_variants} ({success_rate:.1f}%)
Failed: {grand_total_failed}
Images saved to: {OUTPUT_FOLDER}/
Error log: {LOG_FILE}
{'='*60}
"""
    print(summary)
    
    # Append summary to log
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n{summary}")
    except Exception as e:
        print(f"Warning: Couldn't write summary to log: {e}")


if __name__ == "__main__":
    main()