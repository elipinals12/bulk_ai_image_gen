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

- **Dual Shot Types**: Generates both tight cropped product shots and pulled-back lifestyle shots
- **Category-Based Scraping**: Extracts and follows site's native 3-level category hierarchy
- **Global Duplicate Detection**: Tracks products by (SKU, name) to avoid downloading duplicates
- **Hierarchical Organization**: Maintains Top → Mid → Granular folder structure
- **White Background Validation**: Perimeter pixel sampling with 85% threshold
- **AI Image Generation**: Category-specific prompts with studio lighting for realistic settings
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
2. **Generates Two Shot Types** per product:
   - **Tight Cropped**: Product-focused with minimal background
   - **Normal Lifestyle**: Pulled-back room context
3. **Applies Category-Specific Prompts** by looking up in nested JSON
4. **Generates N Variants** per shot type via Gemini API
5. **Saves to Mirrored Structure** preserving the same 3-level hierarchy

### Shot Types Explained

**Tight Cropped Shots** (`v1 - cropped.jpg`, `v2 - cropped.jpg`, etc.):
- Close-up product focus
- Minimal background distraction
- Shows product details and in-use context
- Perfect for thumbnails and product detail pages

**Normal Lifestyle Shots** (`v1.jpg`, `v2.jpg`, etc.):
- Pulled-back perspective showing full room/setting
- More environmental context
- Shows how product fits in space
- Ideal for lifestyle marketing and inspiration

### Test vs Production Mode

**Test Mode** (default):
- Processes **1 product per category** (30 total products)
- Generates **1 cropped + 1 normal** per product (2 variants)
- Cost: ~$2.40 (60 images @ $0.04/image)
- Perfect for validating setup

**Production Mode**:
- Processes **all products in all categories**
- Generates **3 cropped + 3 normal** per product (6 variants, configurable)
- Cost: ~$24 per 100 products (600 images)

### Prompt System

**What Gets Sent to Gemini API:**
1. **Text prompt**: Shot-specific base prompt + category prompt
2. **Reference image**: Original white-background product image (base64 encoded)
3. **Aspect ratio**: From JSON (default: "1:1")
4. **Image size**: From JSON, Pro model only (default: "4K" = 4096px)
5. **Output format**: Always JPEG, saved at 95% quality

**Base Prompts:**

*Cropped Shot Base:*
```
"Professional product photography with tight crop on the item from 
the provided image. Clean backdrop showing product in realistic use, 
sharp focus, high-end aesthetic."
```

*Normal Shot Base:*
```
"Professional lifestyle photograph showing the item from the provided 
image in a realistic styled setting. Sharp focus, high-end aesthetic."
```

**Prompt Philosophy:**
- 🎨 **Style variation built-in** - Prompts are flexible to allow natural variation
- ✨ **Quality-focused** - Concise but effective for professional results
- 🌊 **No running water** - Only wet surfaces where contextually appropriate
- 📐 **Balanced length** - Not too specific, not too vague

**Category-Specific Prompts** (examples):
- **Shower Benches**: "Modern bathroom shower with wet tile surfaces, spa ambiance with ambient lighting, bath products and towels nearby."
- **Coffee Tables**: "Living room with books or coffee on surface, sofa partially visible, natural window light, contemporary interior."
- **Outdoor Benches**: "Garden patio or deck with greenery in background, natural wood or stone surface, warm sunlight."

**All 30 categories have custom prompts** optimized for their specific use case.

### Output Structure

The generator **mirrors the scraper's 3-level folder structure** exactly and creates **separate variants** for cropped and normal shots:

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
                ├── v0 624 - Product Name.jpg        (original copy)
                ├── v1 624 - Product Name - cropped.jpg  (tight shot)
                ├── v2 624 - Product Name - cropped.jpg  (tight shot)
                ├── v3 624 - Product Name - cropped.jpg  (tight shot)
                ├── v1 624 - Product Name.jpg        (lifestyle shot)
                ├── v2 624 - Product Name.jpg        (lifestyle shot)
                └── v3 624 - Product Name.jpg        (lifestyle shot)
```

### Usage

**Test Mode** (1 product per category, 1 of each shot type):
```python
# In generate_images.py:
TEST_MODE = True
```
```bash
python generate_images.py
```

**Production Mode** (all products, 3 of each shot type):
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
- `TEST_MODE = True` → Flash model (~$0.08 for 2 variants × 1 product)
- `TEST_MODE = False` → Pro model (~$0.80-$1.44 for 6 variants × 1 product)

Example production costs (3 cropped + 3 normal = 6 variants each at 4K):
- 100 products: ~$144 (600 images @ $0.24/image)
- 350 products: ~$504 (2,100 images)

**Supported Resolutions (Pro model only):**
- "1K" → 1024px images ($0.134/image)
- "2K" → 2048px images ($0.18/image)
- "4K" → 4096px images ($0.24/image, recommended for print quality)

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
3. **Removes watermarks** from all variants (v1, v2, v3, both cropped and normal)
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
                ├── v0 624 - Product Name.jpg
                ├── v1 624 - Product Name - cropped.jpg  (cleaned)
                ├── v2 624 - Product Name - cropped.jpg  (cleaned)
                ├── v3 624 - Product Name - cropped.jpg  (cleaned)
                ├── v1 624 - Product Name.jpg        (cleaned)
                ├── v2 624 - Product Name.jpg        (cleaned)
                └── v3 624 - Product Name.jpg        (cleaned)

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
REQUEST_DELAY = 0.2  # Delay between API calls
```

**User settings** (in category_prompts.json):
```json
{
  "cropped_variants_per_image": 3,
  "normal_variants_per_image": 3,
  "aspect_ratio": "1:1",
  "image_size": "4K"
}
```

**Note:** In TEST_MODE, these are overridden to 1 of each type regardless of config values.

### watermark_removal.py

```python
INPUT_FOLDER = "generated_images"
OUTPUT_FOLDER = "cleaned_images"
WATERMARK_SIZE = 80       # Pixels from corner to remove
WATERMARK_MARGIN = 10     # Extra margin around watermark
INPAINT_RADIUS = 5        # Radius for inpainting algorithm
```

### category_prompts.json

- `cropped_variants_per_image`: Number of tight product shots (3 recommended)
- `normal_variants_per_image`: Number of lifestyle shots (3 recommended)
- `aspect_ratio`: Image dimensions - "1:1" (square), "16:9" (wide), "9:16" (tall), etc.
- `image_size`: Resolution for Pro model - "1K", "2K", or "4K" (only applies to production mode)
- `base_prompt_cropped`: Global instructions for tight product shots
- `base_prompt_normal`: Global instructions for lifestyle shots
- `categories`: Nested structure with category-specific prompts

**Note:** `image_size` only works with Pro model (production mode). Test mode (Flash model) always generates 1024px images.

---

## Workflow

```bash
# 1. Scrape all products
python scraper.py

# 2. Test generation (1 product per category = 30 products, 2 variants each)
# Make sure TEST_MODE = True in generate_images.py
python generate_images.py

# 3. Remove watermarks (copies to cleaned_images/)
python watermark_removal.py

# 4. Review cleaned_images/ folder
# - Check v1/v2/v3 - cropped.jpg files (tight shots)
# - Check v1/v2/v3.jpg files (lifestyle shots)

# 5. Full production run (all products, 6 variants each)
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

### Naming Convention
- `v0 [name].jpg` - Original white-background image (no watermark)
- `v1 [name] - cropped.jpg` - First tight product shot (watermark removed)
- `v2 [name] - cropped.jpg` - Second tight product shot (watermark removed)
- `v3 [name] - cropped.jpg` - Third tight product shot (watermark removed)
- `v1 [name].jpg` - First lifestyle shot (watermark removed)
- `v2 [name].jpg` - Second lifestyle shot (watermark removed)
- `v3 [name].jpg` - Third lifestyle shot (watermark removed)

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
- Script handles both cropped and normal variants automatically

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
- Generated images: 1024px (test) or up to 4K (production) depending on mode
- **Dual shot types**: Both tight cropped and lifestyle shots generated
- **Visible watermarks**: Google adds "Gemini sparkle" logo to API-generated images (free tier policy)
- **Watermark removal**: Non-destructive - originals preserved, cleaned copies in separate folder
- **Model names verified** as of Jan 2026:
  - `gemini-2.5-flash-image` (stable, production-ready)
  - `gemini-3-pro-image-preview` (preview, best quality available)
- Output always saved as JPEG regardless of input format
- **Flexible prompts** allow natural style variation while maintaining quality
- **No running water** in shots - only wet surfaces where contextually appropriate
- **Balanced prompt length** - concise but effective for professional results

---

## Cost Estimates

**Test Mode** (1 product per category = 30 products, 1 cropped + 1 normal):
- Images generated: 60 (30 products × 2 variants)
- Cost: ~$2.40 @ $0.04/image (Flash model)
- Time: ~10-15 minutes with rate limiting

**Production Mode** (example: 350 products, 3 cropped + 3 normal):
- Images generated: 2,100 (350 products × 6 variants)
- Cost: ~$504 @ $0.24/image (Pro model, 4K resolution)
- Time: ~4-6 hours with rate limiting

**Cost breakdown by resolution (Pro model):**
- 1K: ~$282 (2,100 images @ $0.134/image)
- 2K: ~$378 (2,100 images @ $0.18/image)
- 4K: ~$504 (2,100 images @ $0.24/image) - **recommended**

Monitor real-time usage at: https://aistudio.google.com/