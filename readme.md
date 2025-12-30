# Product Image AI Generation Pipeline

Complete workflow for scraping, regenerating, and organizing product images using AI.

---

## Overview

Three-step pipeline to transform white-background product photos into styled lifestyle images:

1. **Scrape & Organize** - Download white-background images sorted by category *(implemented)*
2. **AI Generation** - Generate styled lifestyle images via Gemini API *(implemented)*
3. **Review & Deploy** - View and select best variants *(planned)*

---

## Setup

### Dependencies

```bash
# For scraper (Step 1)
pip install requests beautifulsoup4 pillow tqdm

# For image generation (Step 2)
pip install requests pillow numpy tqdm
```

### Watermark Removal Setup

Step 2 requires alpha maps for pixel-perfect watermark removal:

1. Download `embedded_assets.hpp` from: https://github.com/allenk/GeminiWatermarkTool
2. Place in `gemini_watermarks/` folder
3. Run: `python extract_alpha_maps.py`
4. This creates `bg_48.png` and `bg_96.png` in `gemini_watermarks/`

### Gemini API Key

Get your free API key from: https://aistudio.google.com/apikey

Add to `generate_images.py`:
```python
GEMINI_API_KEY = "your-key-here"
```

---

## Step 1: Image Scraping (IMPLEMENTED)

### What It Does

Scrapes product listing pages and:
- Extracts product names from catalog listings
- Visits individual product pages to retrieve SKU numbers
- Downloads largest available image (1280x1280)
- Validates white backgrounds via perimeter pixel sampling
- Organizes into category folders as: `SKU - Product Name.jpg`
- Generates organized error log grouped by error type

### White Background Detection

**Method:** Perimeter pixel sampling
- Samples every 20 pixels around all 4 edges (top, bottom, left, right)
- Checks if RGB values ≥ 235 for each sample (catches light grey backgrounds)
- Image passes if ≥85% of samples meet threshold (allows for edge artifacts/shadows)
- Non-white images automatically skipped and deleted

### Category System

Products matched to exactly one category via keyword priority (first match wins). Categories and keywords defined in `category_prompts.json`:

```
shower/   - Shower benches, organizers, caddies
bench/    - Benches, stools (non-shower)
chair/    - Chairs, seating
shelf/    - Wall shelves, floating shelves
outdoor/  - Patio furniture, loungers, dining sets
hamper/   - Laundry hampers
kitchen/  - Cutting boards, knife racks, trivets
storage/  - Storage bins, boxes, trays
mat/      - Floor mats, bath mats
table/    - Coffee/side tables
cabinet/  - Cabinets, stands, racks
other/    - Unmatched items
```

### Log File Format

Errors grouped by type with comprehensive summary:

```
================================================================================
PRODUCT IMAGE SCRAPER - ERROR LOG
================================================================================
Timestamp: 2024-12-30 15:30:45
Source: [configured URL]
================================================================================

================================================================================
BACKGROUND TOO DARK (28 items)
================================================================================

SKU: 624
Product: Shower Shelf
Details: 78.3% white pixels (needs 85.0%)
--------------------------------------------------------------------------------
SKU: 531
Product: Organizer
Details: 82.1% white pixels (needs 85.0%)
--------------------------------------------------------------------------------

================================================================================
DOWNLOAD ERROR (4 items)
================================================================================

SKU: 445
Product: Bath Mat
Details: Connection timeout
--------------------------------------------------------------------------------

================================================================================
SUMMARY
================================================================================

Total products processed:      147
Successfully downloaded:       112 (76.2%)
Skipped (errors):              35 (23.8%)

Error breakdown:
  Non-white background:        28 (19.0%)
  Other errors:                7 (4.8%)

Detailed error categories:
  Background Too Dark: 28 (19.0%)
  Download Error: 4 (2.7%)
  No Image URL: 2 (1.4%)
  No SKU Found: 1 (0.7%)

================================================================================
```

### Usage

```bash
python scraper.py
```

**Output:**
- Images saved to `aquateak_products/` (deleted and recreated each run)
- Error log saved to `scraper_log.txt` (deleted and recreated each run)
- Console displays progress bars with success/skip indicators

### Configuration

All settings in `scraper.py`:
- `BASE_URL` - Product listing page URL
- `TOTAL_PAGES` - Pages to scrape (default: 7)
- `OUTPUT_DIR` - Save location
- `WHITE_THRESHOLD` - RGB threshold (default: 235)
- `WHITE_PERCENTAGE` - Required white pixels (default: 0.85)
- `SAMPLE_INTERVAL` - Sampling frequency (default: 20px)
- `REQUEST_DELAY` - Request delay (default: 0.5s)

---

## Step 2: AI Image Generation (IMPLEMENTED)

### What It Does

Generates styled lifestyle product images using Gemini Image Generation API:
1. Reads original white-background images from input folder
2. For each image:
   - Combines base prompt + category-specific prompt
   - Calls Gemini API with original image as reference
   - Generates N variants (default: 3) with product in styled environment
   - Removes Gemini watermark using reverse alpha blending
   - Saves original as v0, variants as v1, v2, v3, etc.
3. Organizes output into product subfolders by category

### Watermark Removal: Reverse Alpha Blending

Gemini adds a semi-transparent sparkle watermark to all API-generated images. This pipeline uses **reverse alpha blending** for pixel-perfect removal:

**How It Works:**
- Gemini applies watermark using alpha compositing: `watermarked = α × logo + (1 - α) × original`
- We reverse the formula to restore original pixels: `original = watermarked / (1 - α)`
- Alpha maps (`bg_48.png`, `bg_96.png`) contain pre-captured transparency values
- Mathematical restoration produces zero quality loss (vs. inpainting which "guesses")

**Watermark Specifications:**
- Location: Bottom-right corner
- Images ≤1024px (width OR height): 48×48px watermark, 32px margin
- Images >1024px (width AND height): 96×96px watermark, 64px margin

**Why Reverse Alpha vs. Inpainting:**
- Pixel-perfect restoration (no blur or artifacts)
- ~2-5ms processing time (faster than inpainting)
- Preserves text and sharp edges perfectly
- Mathematically exact, not AI guessing

### Prompt Structure

Prompts defined in `category_prompts.json`:

**Base Prompt:** Global instructions for all images
```
"Create a professional lifestyle product photograph showing the item 
from the provided image in a realistic, styled setting. Photorealistic 
lighting, sharp focus, high-end aesthetic."
```

**Category Prompts:** Context-specific environment details
- **shower:** Modern luxury bathroom with water droplets, wet tiles, spa lighting
- **bench:** Entryway/bedroom with throw blanket, natural window light
- **chair:** Elegant dining/living room, cushion, sophisticated interior
- **kitchen:** Marble countertop, fresh ingredients, bright lighting
- **outdoor:** Patio deck, lush greenery, golden hour sunlight
- **mat:** Overhead angle on bathroom floor with water droplets
- **table:** Living room with magazines, coffee, large windows
- **cabinet:** Luxury bathroom wall with organized toiletries
- **other:** Appropriate upscale setting matching item function

**Final Prompt Sent to API:**
```python
prompt = base_prompt + " " + categories[category_name]["prompt"]
```

### Output Structure

```
generated_images/
├── shower/
│   ├── 624 - Product Name Here/
│   │   ├── v0 624 - Product Name Here.jpg  (original)
│   │   ├── v1 624 - Product Name Here.jpg  (AI variant 1)
│   │   ├── v2 624 - Product Name Here.jpg  (AI variant 2)
│   │   └── v3 624 - Product Name Here.jpg  (AI variant 3)
│   └── 531 - Another Product/
│       ├── v0 531 - Another Product.jpg
│       ├── v1 531 - Another Product.jpg
│       ├── v2 531 - Another Product.jpg
│       └── v3 531 - Another Product.jpg
├── shelf/
├── outdoor/
└── [all other categories...]
```

**Test mode output:** Creates 3 category folders, each with 1 product subfolder containing v0-v3 (12 total images)

### Usage

**Test Mode (3 sample images from different categories):**
```python
# In generate_images.py, set:
TEST_MODE = True
```
```bash
python generate_images.py
```
- Processes **3 images** (one from each of 3 different categories)
- Uses **fast model** for cost savings (~$0.04/image)
- Total cost: **~$0.36** (9 variants)
- Tests full folder structure and watermark removal

**Full Production Run (all images):**
```python
# In generate_images.py, set:
TEST_MODE = False
```
```bash
python generate_images.py
```
- Processes **all images** in all categories
- Uses **Pro model** for highest quality (~$0.13/image)
- Cost depends on number of products (e.g., 100 products × 3 variants = $40)

**Output:**
- Images saved to `generated_images/` (deleted and recreated each run)
- Error log saved to `generation_log.txt`
- Console displays nested progress bars with success/failure indicators
- Test mode creates output structure with 3 category folders (1 product each)

### Configuration

All settings in `generate_images.py`:
- `GEMINI_API_KEY` - Your Gemini API key (required)
- `GEMINI_MODEL_TEST` - Fast model for testing (default: `gemini-2.5-flash-image`)
- `GEMINI_MODEL_PRODUCTION` - Pro model for production (default: `gemini-3-pro-image-preview`)
- `INPUT_FOLDER` - Source images folder (default: `aquateak_products`)
- `OUTPUT_FOLDER` - Generated images folder (default: `generated_images`)
- `VARIANTS_PER_IMAGE` - Variants per product (default: 3)
- `REQUEST_DELAY` - Delay between API calls (default: 1.0s)
- `TEST_MODE` - Test with 1 image + fast model (default: True)

**Model auto-selection:**
- `TEST_MODE = True` → Uses fast model (~$0.04/image, ~$0.12 for 3 variants)
- `TEST_MODE = False` → Uses Pro model (~$0.13/image, ~$0.40 for 3 variants)

Model comparison:
- **Fast** (`gemini-2.5-flash-image`) - Quick generations, good quality, cheap
- **Pro** (`gemini-3-pro-image-preview`) - Best quality, photorealism, text rendering

---

## Step 3: Review & Deploy (PLANNED)

### Planned Functionality

- Web-based viewer to compare original vs. all variants side-by-side
- Select/reject individual variants
- Batch export approved images for website upload
- Quality control tracking and notes

---

## File Structure

```
project/
├── scraper.py                    # Step 1: Scrape product images
├── generate_images.py            # Step 2: Generate AI variants
├── extract_alpha_maps.py         # Helper: Extract PNG files from C++ header
├── category_prompts.json         # Category keywords and prompts
├── scraper_log.txt               # Scraper error log (auto-generated)
├── generation_log.txt            # Generation error log (auto-generated)
├── gemini_watermarks/            # Watermark removal assets
│   ├── embedded_assets.hpp       # Downloaded from GitHub
│   ├── bg_48.png                 # Extracted alpha map (small watermarks)
│   └── bg_96.png                 # Extracted alpha map (large watermarks)
├── aquateak_products/            # Scraped images (auto-generated)
│   ├── shower/
│   ├── bench/
│   ├── chair/
│   └── [10 more categories]
└── generated_images/             # AI-generated variants (auto-generated)
    ├── shower/
    │   └── [product subfolders with v0-v3 variants]
    └── [all other categories]
```

---

## Workflow Summary

### Quick Start

```bash
# 1. Scrape product images
python scraper.py

# 2. Extract watermark alpha maps (one-time setup)
python extract_alpha_maps.py

# 3. Test AI generation (3 sample images, fast model, ~$0.36)
# TEST_MODE = True in generate_images.py
python generate_images.py

# 4. Run full generation (all images, Pro model, ~$40 for 100 products)
# Set TEST_MODE = False in generate_images.py
python generate_images.py
```

### Full Pipeline

1. **Configure categories** in `category_prompts.json`
2. **Configure scraper** with product catalog URL in `scraper.py`
3. **Run scraper** → Downloads white-background images
4. **Review scraper log** → Check what was skipped and why
5. **Extract alpha maps** → One-time setup for watermark removal
6. **Test generation** → Verify API key, prompts, and watermark removal (3 sample images)
7. **Review test outputs** → Check quality and folder structure
8. **Run full generation** → Process all images with Pro model
9. **Review generation log** → Check for API failures
10. **Review all outputs** → Compare variants and select best

---

## Technical Details

### Filename Sanitization
- Inch symbol `"` → ` inch`
- Special characters (`/`, `\`, `:`, `*`, `?`, `<`, `>`, `|`) removed or replaced
- Trademark symbols (™, ®) stripped
- Multiple spaces collapsed to single space

### Image Requirements
- Source images must have white/light backgrounds (≥85% white perimeter)
- RGB threshold: 235 (catches light grey)
- Original images preserved as v0 in output

### Rate Limiting
- Scraper: 0.5s delay between requests
- Generator: 1.0s delay between API calls (configurable)
- Adjust `REQUEST_DELAY` if hitting rate limits

### API Costs
Gemini API charges per image generation:
- **Fast model:** ~$0.04/image
- **Pro model:** ~$0.13/image (1K-2K resolution)

The script auto-selects model based on TEST_MODE:
- Test mode uses fast model (~$0.12 for 3 variants of 1 image)
- Production mode uses Pro model (~$0.40 per product × number of products)

Example cost for 100 products with 3 variants each:
- Fast: ~$12
- Pro: ~$40

Monitor usage at: https://aistudio.google.com/

---

## Troubleshooting

**Scraper Issues:**
- Check `scraper_log.txt` for organized error breakdown
- "Background Too Dark" errors show exact white pixel percentage
- Adjust `WHITE_THRESHOLD` or `WHITE_PERCENTAGE` if too many false rejections

**Generation Issues:**
- Check `generation_log.txt` for API errors
- Verify API key is set correctly
- Ensure alpha maps exist in `gemini_watermarks/`
- Use TEST_MODE (3 images, fast model, ~$0.36) to debug before full run
- Check API quota at https://aistudio.google.com/

**Watermark Removal Issues:**
- Ensure `bg_48.png` and `bg_96.png` exist in `gemini_watermarks/`
- Run `extract_alpha_maps.py` if files are missing
- Script auto-detects correct watermark size based on image dimensions

---

## Configuration Files

### category_prompts.json

```json
{
  "base_prompt": "Global prompt for all images...",
  "categories": {
    "shower": {
      "keywords": ["shower"],
      "prompt": "Category-specific environment description..."
    },
    ...
  },
  "generation_settings": {
    "attempts_per_image": 3,
    "model": "gemini",
    "aspect_ratio": "1:1",
    "output_mime_type": "image/jpeg"
  }
}
```

**Structure:**
- `base_prompt` - Applied to all images
- `categories[name].keywords` - Matching keywords for categorization
- `categories[name].prompt` - Category-specific environment details
- `generation_settings.aspect_ratio` - Image aspect ratio (1:1, 16:9, etc.)
- `generation_settings.output_mime_type` - Output format

---

## Notes

- All folders recreated fresh on each run (no incremental updates)
- SKU numbers are unique product identifiers
- Categories are mutually exclusive (first keyword match wins)
- Only the main product image is downloaded (lifestyle shots skipped)
- Gemini watermark is mandatory on free/Pro API tier (cannot be disabled)
- Images stored at maximum available resolution (typically 1280x1280)
- Customize categories, keywords, and prompts in `category_prompts.json` for your product line
- Configure source URL in `scraper.py` `BASE_URL` variable