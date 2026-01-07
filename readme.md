# Product Image AI Generation Pipeline

Complete workflow for scraping, regenerating, and organizing product images using AI.

---

## Overview

Three-step pipeline to transform white-background product photos into styled lifestyle images:

1. **Scrape & Organize** - Download images from site's native category structure *(implemented)*
2. **AI Generation** - Generate styled lifestyle images via Gemini API *(implemented)*
3. **Watermark Removal** - Clean watermarks from generated images *(implemented)*
4. **Review & Deploy** - View and select best variants *(planned)*

---

## Key Features

- **Category-Based Scraping**: Extracts and follows site's native 3-level category hierarchy
- **Global Duplicate Detection**: Tracks products by (SKU, name) to avoid downloading duplicates
- **Hierarchical Organization**: Maintains Top → Mid → Granular folder structure
- **White Background Validation**: Perimeter pixel sampling with 85% threshold
- **AI Image Generation**: Category-specific prompts for realistic lifestyle settings
- **Watermark Removal**: OpenCV inpainting to clean bottom-right watermarks
- **Non-destructive Processing**: Original images preserved, cleaned copies in separate folder

---

## Setup

### Dependencies

```bash
pip install requests beautifulsoup4 pillow tqdm opencv-python
```

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

### Usage

```bash
python scraper.py
```

**Output:**
- Images saved to `aquateak_products/` (recreated fresh each run)
- Error log saved to `scraper_log.txt`
- Console shows progress bars with duplicate detection

---

## Step 2: AI Image Generation

### How It Works

1. **Traverses 3-Level Hierarchy** matching scraper output structure
2. **Applies Category-Specific Prompts** by looking up in nested JSON
3. **Generates N Variants** (default: 3) per product via Gemini API
4. **Saves to Mirrored Structure** preserving the same 3-level hierarchy

### Test vs Production Mode

**Test Mode** (default):
- Processes **1 product per category** (30 total products)
- Cost: ~$3.60 (90 images @ $0.04/image)
- Perfect for validating setup

**Production Mode**:
- Processes **all products in all categories**
- Cost: ~$40 per 100 products (300 images)

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

### Output Structure

The generator **mirrors the scraper's 3-level folder structure** exactly:

```
Input (from scraper):
aquateak_products/
└── Bathroom/
    └── Bathroom Furniture and Storage/
        └── Shower Benches/
            └── 624 - Product Name.jpg

Output (from generator):
generated_images/
└── Bathroom/
    └── Bathroom Furniture and Storage/
        └── Shower Benches/
            └── 624 - Product Name/
                ├── v0 624 - Product Name.jpg  (original copy)
                ├── v1 624 - Product Name.jpg  (AI variant 1)
                ├── v2 624 - Product Name.jpg  (AI variant 2)
                └── v3 624 - Product Name.jpg  (AI variant 3)
```

### Usage

**Test Mode** (1 product per category):
```python
# In generate_images.py:
TEST_MODE = True
```
```bash
python generate_images.py
```

**Production Mode** (all products):
```python
# In generate_images.py:
TEST_MODE = False
```
```bash
python generate_images.py
```

### API Costs & Watermarks

**Gemini API charges per image generation:**
- **Test model** (`gemini-2.5-flash-image`): $0.039/image, generates 1024px
- **Production model** (`gemini-3-pro-image-preview`): $0.134-$0.24/image depending on resolution

**Important:** All Gemini API-generated images include visible "Gemini sparkle" watermarks in bottom-right corner. This is a Google policy for free-tier API users. See Step 3 for removal.

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

## Step 3: Watermark Removal

### How It Works

1. **Copies entire folder structure** from `generated_images/` to `cleaned_images/`
2. **Preserves v0 originals** (copies without modification)
3. **Removes watermarks** from v1, v2, v3... using OpenCV inpainting
4. **Original files stay untouched** in `generated_images/`

### Method

Uses **OpenCV INPAINT_TELEA** algorithm:
- Creates mask over bottom-right corner (80px region)
- Intelligently fills masked area based on surrounding pixels
- Fast processing (~50-100ms per image)
- Results may show slight blur in corner

### Output Structure

```
cleaned_images/           (NEW - watermark-free copies)
└── Bathroom/
    └── Bathroom Furniture and Storage/
        └── Shower Benches/
            └── 624 - Product Name/
                ├── v0 624 - Product Name.jpg  (copied, no watermark originally)
                ├── v1 624 - Product Name.jpg  (cleaned)
                ├── v2 624 - Product Name.jpg  (cleaned)
                └── v3 624 - Product Name.jpg  (cleaned)

generated_images/         (ORIGINAL - preserved untouched)
└── [same structure with watermarks intact]
```

### Usage

```bash
python watermark_removal.py
```

### Adjustments

If watermarks aren't fully removed, adjust in `watermark_removal.py`:
```python
WATERMARK_SIZE = 100  # Increase if watermark bigger
WATERMARK_MARGIN = 20  # More margin for safety
INPAINT_RADIUS = 7    # Larger radius for better blending
```

---

## Step 4: Review & Deploy (PLANNED)

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
TEST_MODE = True                  # False for production (all products)
```

**Advanced settings** (usually don't change):
```python
GEMINI_MODEL_TEST = "gemini-2.5-flash-image"           # Fast & cheap (~$0.04/image)
GEMINI_MODEL_PRODUCTION = "gemini-3-pro-image-preview" # Best quality (~$0.13/image)
REQUEST_DELAY = 5.0  # Increased to avoid rate limits
```

**User settings** (in category_prompts.json):
```json
{
  "variants_per_image": 3,
  "aspect_ratio": "1:1",
  "image_size": "2K"
}
```

### watermark_removal.py

```python
INPUT_FOLDER = "generated_images"
OUTPUT_FOLDER = "cleaned_images"
WATERMARK_SIZE = 80       # Pixels from corner to remove
WATERMARK_MARGIN = 10     # Extra margin around watermark
INPAINT_RADIUS = 5        # Radius for inpainting algorithm
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
python scraper.py

# 2. Test generation (1 product per category = 30 products)
# Make sure TEST_MODE = True in generate_images.py
python generate_images.py

# 3. Remove watermarks (copies to cleaned_images/)
python watermark_removal.py

# 4. Review cleaned_images/ folder

# 5. Full production run (all products)
# Set TEST_MODE = False in generate_images.py
python generate_images.py
python watermark_removal.py
```

---

## Technical Details

### Output Format
- All generated images saved as **JPEG** at 95% quality
- Input images can be JPG or PNG (converted during processing)
- Watermark-removed variants maintain original quality

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
- Use TEST_MODE to debug before full run
- If "prompt not found" errors, verify folder names match JSON keys exactly
- **429 Rate Limit Errors**: Wait until midnight Pacific Time for quota reset, or enable billing

**Watermark Removal Issues:**
- If watermarks not fully removed, increase `WATERMARK_SIZE` to 100-120
- Increase `INPAINT_RADIUS` to 7-10 for better blending
- Check that `cleaned_images/` folder was created
- Originals remain untouched in `generated_images/`

**Folder Structure Mismatch:**
- Generator expects same 3-level structure as scraper creates
- Folder names must match (case-sensitive)
- Check that `aquateak_products/` has Top/Mid/Granular structure
- Verify JSON category keys match folder names (e.g., "Bathroom Furniture and Storage")

**Category Structure:**
- If site navigation changes, scraper auto-extracts new structure
- Update prompts in `category_prompts.json` if new categories appear

---

## Important Notes

- All folders recreated fresh each run (no incremental updates)
- Global deduplication prevents duplicate downloads
- 30 custom prompts for realistic lifestyle settings
- Hierarchical organization matches site structure
- Images stored at 1280x1280 from scraper (max available)
- Generated images: 1024px (test) or 2K (production) depending on mode
- **Visible watermarks**: Google adds "Gemini sparkle" logo to API-generated images (free tier policy)
- **Watermark removal**: Non-destructive - originals preserved, cleaned copies in separate folder
- **Model names verified** as of Jan 2026:
  - `gemini-2.5-flash-image` (stable, production-ready)
  - `gemini-3-pro-image-preview` (preview, best quality available)
- Output always saved as JPEG regardless of input format

---

## Cost Estimates

**Test Mode** (1 product per category = 30 products):
- Images generated: 90 (30 products × 3 variants)
- Cost: ~$3.60 @ $0.04/image (Flash model)
- Time: ~15-20 minutes with rate limiting

**Production Mode** (example: 350 products):
- Images generated: 1,050 (350 products × 3 variants)
- Cost: ~$140 @ $0.13/image (Pro model, 2K resolution)
- Time: ~2-3 hours with rate limiting

Monitor real-time usage at: https://aistudio.google.com/