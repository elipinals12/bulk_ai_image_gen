# Product Image AI Generation Pipeline

Complete workflow for scraping, regenerating, and organizing product images using AI.

---

## Overview

Three-step pipeline to transform white-background product photos into styled lifestyle images:

1. **Scrape & Organize** - Download images from site's native category structure *(implemented)*
2. **AI Generation** - Generate styled lifestyle images via Gemini API *(implemented)*
3. **Review & Deploy** - View and select best variants *(planned)*

---

## Key Features

- **Category-Based Scraping**: Extracts and follows site's native 3-level category hierarchy
- **Global Duplicate Detection**: Tracks products by (SKU, name) to avoid downloading duplicates
- **Hierarchical Organization**: Maintains Top → Mid → Granular folder structure
- **White Background Validation**: Perimeter pixel sampling with 85% threshold
- **Reverse Alpha Blending**: Pixel-perfect watermark removal for AI-generated images
- **Custom Prompts**: 30 category-specific prompts for realistic lifestyle settings

---

## Setup

### Dependencies

```bash
pip install requests beautifulsoup4 pillow tqdm numpy
```

### Watermark Removal Setup

1. Download `embedded_assets.hpp` from: https://github.com/allenk/GeminiWatermarkTool
2. Place in project folder
3. Run: `python extract_alpha_maps.py`
4. This creates `bg_48.png` and `bg_96.png`

### Gemini API Key

Get free API key from: https://aistudio.google.com/apikey

Add to `generate_images.py`:
```python
GEMINI_API_KEY = "your-key-here"
```

---

## Step 1: Image Scraping

### How It Works

1. **Extracts Category Structure** from homepage navigation
2. **Scrapes Each Category** with pagination support
3. **Global Deduplication** - First occurrence downloaded, subsequent skipped
4. **White Background Validation** - 85% white pixel threshold
5. **Hierarchical Folders** - Top/Mid/Granular structure

### Category Structure (30 Categories)

**Bathroom (9 categories)**
- Bathroom Furniture & Storage
  - Shower Benches
  - Shower Organizers & Caddies
  - Floating Wall Shelves
  - Storage Bins & Trays
  - Storage
- Bath Accessories
  - Floor Mats
  - Waste Baskets & Hampers
  - Towel Racks
  - Side Tables

**Indoor (11 categories)**
- Entryway
  - Entryway Benches
  - Key Holders
- Living Room
  - Coffee Tables
  - Shelving
  - Storage
  - Tissue Boxes & Hangers
  - Waste Baskets & Hampers
- Kitchen
  - Bar & Counter Stools
  - Countertop Accessories
  - Dining
  - Floor Mats

**Outdoor (10 categories)**
- Furniture
  - Benches
  - Daybeds
  - Dining Tables & Chairs
  - Games
  - Garden
  - Lighting
  - Lounge Chairs, Stools & Ottomans
  - Parasols
  - Sofas & Loveseats
  - Storage Chests

### Folder Structure Output

```
aquateak_products/
├── Bathroom/
│   ├── Bathroom Furniture and Storage/
│   │   ├── Shower Benches/
│   │   │   └── [product images]
│   │   ├── Shower Organizers and Caddies/
│   │   └── ...
│   └── Bath Accessories/
│       ├── Floor Mats/
│       └── ...
├── Indoor/
│   ├── Entryway/
│   ├── Living Room/
│   └── Kitchen/
└── Outdoor/
    └── Furniture/
        ├── Benches/
        └── ...
```

### Duplicate Detection

Products appearing in multiple categories are **downloaded once** (first occurrence) and **logged as duplicates** for subsequent appearances.

**Example:**
- Floor Mat found in `Bathroom/Bath Accessories/Floor Mats` → Downloaded
- Same Floor Mat found in `Indoor/Kitchen/Floor Mats` → Skipped, logged as duplicate

### Usage

```bash
python scraper.py
```

**Output:**
- Images saved to `aquateak_products/` (recreated fresh each run)
- Error log saved to `scraper_log.txt`
- Console shows progress bars with duplicate detection

### Log File Format

```
================================================================================
PRODUCT IMAGE SCRAPER - ERROR LOG
================================================================================
Timestamp: 2025-01-03 12:00:00
Source: https://aquateak.com/
================================================================================

================================================================================
DUPLICATE PRODUCT (27 items)
================================================================================

SKU: 1258
Product: Grate-Mist™ Kitchen Anti-Fatigue Teak Floor Mat
Details: Already downloaded in: Bathroom/Bath Accessories/Floor Mats
--------------------------------------------------------------------------------
...

================================================================================
SUMMARY
================================================================================

Total products found:          450
Unique products (deduplicated):400
Successfully downloaded:       350 (87.5%)
Skipped (errors):              50
Duplicates detected:           50

Error breakdown:
  Non-white background:        20
  Duplicate products:          27
  Other errors:                3
================================================================================
```

---

## Step 2: AI Image Generation

### How It Works

1. **Traverses 3-Level Hierarchy** matching scraper output structure
   - Loops through `Top/Mid/Granular` folders automatically
   - Example: `Bathroom/Bathroom Furniture and Storage/Shower Benches/`
2. **Applies Category-Specific Prompts** by looking up in nested JSON
   - Finds prompt at: `config["categories"]["Bathroom"]["Bathroom Furniture and Storage"]["Shower Benches"]["prompt"]`
3. **Generates N Variants** (default: 3) per product via Gemini API
   - Sends: base_prompt + category_prompt + original image + aspect_ratio + image_size
4. **Removes Watermarks** using reverse alpha blending
5. **Saves to Mirrored Structure** preserving the same 3-level hierarchy
   - Input: `aquateak_products/Bathroom/.../Shower Benches/624 - Product.jpg`
   - Output: `generated_images/Bathroom/.../Shower Benches/624 - Product/v0...v3.jpg`

### Prompt System

**What Gets Sent to Gemini API:**
1. **Text prompt**: `base_prompt` + category-specific `prompt`
2. **Reference image**: Original white-background product image (base64 encoded)
3. **Aspect ratio**: From JSON (default: "1:1")
4. **Image size**: From JSON, Pro model only (default: "2K" = 2048px)
5. **Output format**: Always JPEG, saved at 95% quality

**Base Prompt** (applied to all):
```
"Create a professional lifestyle product photograph showing the item 
from the provided image in a realistic, styled setting. Photorealistic 
lighting, sharp focus, high-end aesthetic."
```

**Category-Specific Prompts** (examples):
- **Shower Benches**: "Modern luxury bathroom shower with water droplets, wet tiles, steam effects, spa lighting..."
- **Coffee Tables**: "Upscale living room with design books, coffee cup, large windows with natural light..."
- **Outdoor Benches**: "Beautiful patio with lush greenery, warm golden hour sunlight, outdoor living atmosphere..."

**All 30 categories have custom prompts** optimized for their specific use case.

### Watermark Removal

**Reverse Alpha Blending** mathematically restores original pixels:
- Formula: `original = watermarked / (1 - α)`
- Alpha maps contain pre-captured transparency values
- Zero quality loss vs. inpainting (AI guessing)
- ~2-5ms processing time per image

### Output Structure

The generator **mirrors the scraper's 3-level folder structure** exactly:

```
Input (from scraper):
aquateak_products/
├── Bathroom/
│   └── Bathroom Furniture and Storage/
│       └── Shower Benches/
│           └── 624 - Product Name.jpg

Output (from generator):
generated_images/
├── Bathroom/
│   └── Bathroom Furniture and Storage/
│       └── Shower Benches/
│           └── 624 - Product Name/
│               ├── v0 624 - Product Name.jpg  (original copy)
│               ├── v1 624 - Product Name.jpg  (AI variant 1)
│               ├── v2 624 - Product Name.jpg  (AI variant 2)
│               └── v3 624 - Product Name.jpg  (AI variant 3)
```

**How it works:**
- Generator automatically traverses all 3 folder levels
- Looks up prompt using: `categories[Top][Mid][Granular]["prompt"]`
- Creates matching output structure with product subfolders
- Each product gets v0 (original) + v1-vN (AI variants)

### Usage

**Test Mode** (3 categories, fast):
```python
# In generate_images.py:
TEST_MODE = True
```
```bash
python generate_images.py
```

**Production Mode** (all images):
```python
# In generate_images.py:
TEST_MODE = False
```
```bash
python generate_images.py
```

### API Costs

Gemini API charges per image generation:
- **Test model** (`gemini-2.5-flash-image`): $0.039/image, generates 1024px
- **Production model** (`gemini-3-pro-image-preview`): $0.134-$0.24/image depending on resolution

Script auto-selects model based on `TEST_MODE`:
- `TEST_MODE = True` → Flash model (~$0.12 for 3 variants × 1 product)
- `TEST_MODE = False` → Pro model (~$0.40-$0.72 for 3 variants × 1 product)

Example production costs (3 variants each at 2K):
- 100 products: ~$40
- 350 products: ~$140

**Supported Resolutions (Pro model only):**
- "1K" → 1024px images ($0.134/image)
- "2K" → 2048px images ($0.18/image, recommended)
- "4K" → 4096px images ($0.24/image, for print quality)

**Supported Aspect Ratios (both models):**
- Square: "1:1"
- Portrait: "2:3", "3:4", "4:5", "9:16"
- Landscape: "3:2", "4:3", "5:4", "16:9", "21:9"

Monitor usage: https://aistudio.google.com/

---

## Step 3: Review & Deploy (PLANNED)

- Web-based viewer for side-by-side comparison
- Select/reject variants
- Batch export for website upload

---

## Configuration

### scraper.py

```python
BASE_URL = "https://aquateak.com"
WHITE_THRESHOLD = 235        # RGB threshold for white detection
WHITE_PERCENTAGE = 0.85      # 85% of perimeter must be white
REQUEST_DELAY = 0.5          # Seconds between requests
```

### generate_images.py

**Settings to change:**
```python
GEMINI_API_KEY = "your-key-here"  # Required - get from ai.google.dev
TEST_MODE = True                  # False for production
```

**Advanced settings** (usually don't change):
```python
GEMINI_MODEL_TEST = "gemini-2.5-flash-image"           # Fast & cheap (~$0.04/image)
GEMINI_MODEL_PRODUCTION = "gemini-3-pro-image-preview" # Best quality (~$0.13/image)
REQUEST_DELAY = 1.0
```

**User settings** (in category_prompts.json):
```json
{
  "variants_per_image": 3,
  "aspect_ratio": "1:1",
  "image_size": "2K"
}
```

### category_prompts.json

- `variants_per_image`: How many AI variants per product (3 recommended)
- `aspect_ratio`: Image dimensions - "1:1" (square), "16:9" (wide), "9:16" (tall), etc.
- `image_size`: Resolution for Pro model - "1K", "2K", or "4K" (only applies to production mode)
- `base_prompt`: Global instructions applied to all images
- `categories`: Nested structure with category-specific prompts

**Note:** `image_size` only works with Pro model (production mode). Test mode (Flash model) always generates 1024px images.

---

## Workflow

```bash
# 1. Scrape all products
python3 scraper.py

# 2. Extract alpha maps (one-time setup)
python3 extract_alpha_maps.py

# 3. Test generation (3 images, already in test mode)
# Add API key to generate_images.py
python3 generate_images.py

# 4. Full production run
# Set TEST_MODE = False in generate_images.py
python3 generate_images.py
```

---

## Technical Details

### Output Format
- All generated images saved as **JPEG** at 95% quality
- Input images can be JPG or PNG (converted during processing)
- Watermark removed variants maintain original quality

### White Background Detection

- **Method**: Perimeter pixel sampling
- **Samples**: Every 20px along all 4 edges
- **Threshold**: RGB ≥ 235 (catches light grey)
- **Pass Rate**: 85% of samples must be white

### Duplicate Detection

- **Tracking**: Global dictionary with (SKU, name) keys
- **Logic**: First occurrence → download, subsequent → skip & log
- **Benefit**: No duplicate images, clear duplicate report

### Filename Sanitization

- Inch symbol `"` → ` inch`
- Special chars (`/`, `\`, `:`, etc.) → removed
- Trademark symbols → stripped
- Folder names: `&` → `and`

### Pagination Support

Automatically detects and scrapes all pages for each category until no "next page" button found.

---

## Troubleshooting

**Scraper Issues:**
- Check `scraper_log.txt` for organized error breakdown
- "Background Too Dark" shows exact white pixel percentage
- Adjust `WHITE_THRESHOLD` or `WHITE_PERCENTAGE` if needed

**Generation Issues:**
- Check `generation_log.txt` for API errors
- Verify API key is set in `generate_images.py`
- Ensure alpha maps exist in `gemini_watermarks/` folder
- Use TEST_MODE to debug before full run
- If "prompt not found" errors, verify folder names match JSON keys exactly

**Folder Structure Mismatch:**
- Generator expects same 3-level structure as scraper creates
- Folder names must match (case-sensitive)
- Check that `aquateak_products/` has Top/Mid/Granular structure
- Verify JSON category keys match folder names (e.g., "Bathroom Furniture and Storage")

**Category Structure:**
- If site navigation changes, scraper auto-extracts new structure
- Update prompts in `category_prompts.json` if new categories appear

---

## Notes

- All folders recreated fresh each run (no incremental updates)
- Global deduplication prevents duplicate downloads
- 30 custom prompts for realistic lifestyle settings
- Hierarchical organization matches site structure
- Watermark removal is pixel-perfect (no quality loss)
- Images stored at 1280x1280 from scraper (max available)
- Generated images: 1024px (test) or 2K (production) depending on mode
- **Model names verified** as of Jan 2026:
  - `gemini-2.5-flash-image` (stable, production-ready)
  - `gemini-3-pro-image-preview` (preview, best quality available)
- Output always saved as JPEG regardless of input format