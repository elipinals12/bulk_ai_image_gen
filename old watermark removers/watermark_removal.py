"""
Watermark Removal Script
Removes Gemini sparkle watermark from generated images using inpainting.
Processes all non-v0 images in generated_images/ folder structure.
"""

import os
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm

# ============================================================================
# Configuration
# ============================================================================

INPUT_FOLDER = "generated_images"
OUTPUT_FOLDER = "cleaned_images"  # New folder for watermark-free copies
WATERMARK_SIZE = 80  # Pixels from corner to remove (adjust if needed)
WATERMARK_MARGIN = 10  # Extra margin around watermark
INPAINT_RADIUS = 5  # Radius for inpainting algorithm

# ============================================================================
# Helper Functions
# ============================================================================

def should_process_file(filename):
    """Check if file should be processed (skip v0 originals)."""
    name_lower = filename.lower()
    
    # Must be image file
    if not name_lower.endswith(('.jpg', '.jpeg', '.png')):
        return False
    
    # Skip v0 files (originals)
    if filename.startswith('v0 '):
        return False
    
    # Process v1, v2, v3, etc.
    if filename.startswith('v'):
        try:
            # Check if it's v{number}
            variant_num = filename.split()[0][1:]  # Get number after 'v'
            int(variant_num)  # Must be valid integer
            return True
        except (ValueError, IndexError):
            return False
    
    return False


def remove_watermark(input_path, output_path):
    """Remove watermark from bottom-right corner using inpainting."""
    try:
        # Read image
        img = cv2.imread(str(input_path))
        if img is None:
            return False, "Failed to read image"
        
        height, width = img.shape[:2]
        
        # Create mask for watermark region (bottom-right corner)
        mask = np.zeros((height, width), dtype=np.uint8)
        
        # Define watermark region with margin
        x1 = max(0, width - WATERMARK_SIZE - WATERMARK_MARGIN)
        y1 = max(0, height - WATERMARK_SIZE - WATERMARK_MARGIN)
        x2 = width
        y2 = height
        
        # Mark watermark area in mask (255 = area to inpaint)
        mask[y1:y2, x1:x2] = 255
        
        # Apply inpainting to remove watermark
        # INPAINT_TELEA is fast and works well for small areas
        result = cv2.inpaint(img, mask, INPAINT_RADIUS, cv2.INPAINT_TELEA)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save to new location
        cv2.imwrite(str(output_path), result, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        return True, "Success"
        
    except Exception as e:
        return False, str(e)


def process_folder_structure():
    """Walk through folder structure and process all applicable images."""
    import shutil
    
    if not os.path.exists(INPUT_FOLDER):
        print(f"✗ ERROR: Folder '{INPUT_FOLDER}' not found")
        print("Run generate_images.py first")
        return
    
    # Delete existing output folder for fresh start
    if os.path.exists(OUTPUT_FOLDER):
        print(f"Deleting existing folder: {OUTPUT_FOLDER}/")
        shutil.rmtree(OUTPUT_FOLDER)
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    print(f"Created fresh output folder: {OUTPUT_FOLDER}/\n")
    
    print("="*60)
    print("Watermark Removal - Processing Generated Images")
    print("="*60)
    print(f"Input folder: {INPUT_FOLDER}/")
    print(f"Output folder: {OUTPUT_FOLDER}/")
    print(f"Watermark size: {WATERMARK_SIZE}px")
    print(f"Processing: v1, v2, v3... (copying v0 originals)\n")
    
    # Collect all files to process
    files_to_process = []
    files_to_copy = []
    
    for root, dirs, files in os.walk(INPUT_FOLDER):
        for filename in files:
            file_path = os.path.join(root, filename)
            # Calculate relative path and output path
            rel_path = os.path.relpath(file_path, INPUT_FOLDER)
            output_path = os.path.join(OUTPUT_FOLDER, rel_path)
            
            if should_process_file(filename):
                files_to_process.append((file_path, output_path))
            elif filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                # Copy v0 originals without processing
                files_to_copy.append((file_path, output_path))
    
    if not files_to_process and not files_to_copy:
        print("✗ No files found to process")
        print("Make sure generate_images.py has created v1, v2, v3... files")
        return
    
    print(f"Found {len(files_to_process)} images to clean")
    print(f"Found {len(files_to_copy)} originals to copy\n")
    
    # Copy v0 originals first
    print("Copying original images (v0)...")
    for src, dst in tqdm(files_to_copy, desc="Copying originals", unit="img"):
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        except Exception as e:
            tqdm.write(f"  ✗ Failed to copy: {os.path.basename(src)} - {e}")
    
    # Process watermarked images
    print("\nRemoving watermarks...")
    successful = 0
    failed = 0
    
    for input_path, output_path in tqdm(files_to_process, desc="Removing watermarks", unit="img"):
        success, message = remove_watermark(input_path, output_path)
        
        if success:
            successful += 1
        else:
            failed += 1
            tqdm.write(f"  ✗ Failed: {os.path.basename(input_path)} - {message}")
    
    # Summary
    total = successful + failed
    success_rate = (successful / total * 100) if total > 0 else 0
    
    summary = f"""
{'='*60}
WATERMARK REMOVAL COMPLETE
{'='*60}
Successfully processed: {successful} / {total} ({success_rate:.1f}%)
Failed: {failed}
Originals copied: {len(files_to_copy)}
Output folder: {OUTPUT_FOLDER}/
{'='*60}
"""
    print(summary)


def main():
    """Main entry point."""
    try:
        process_folder_structure()
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")


if __name__ == "__main__":
    main()