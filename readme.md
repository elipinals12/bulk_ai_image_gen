# AquaTeak Product Image Pipeline

Complete workflow for scraping, regenerating, and organizing product images using AI.

---

## Overview

Three-step pipeline to update product photos from aquateak.com:

1. **Scrape & Organize** - Download white-background images sorted by category *(implemented)*
2. **AI Generation** - Generate styled lifestyle images via Gemini API *(planned)*
3. **Review & Deploy** - View and select best variants *(planned)*

---

## Step 1: Image Scraping (IMPLEMENTED)

### Functionality

Scrapes 7 pages of aquateak.com/all-1/ and:
- Extracts product name from listing pages
- Visits individual product pages to retrieve SKU numbers
- Downloads largest available image (1280x1280)
- Validates white backgrounds via perimeter sampling
- Organizes into category folders as: `SKU - Product Name.jpg`
- Logs all skips/errors to `scraper_log.txt` with SKU, product name, and reason
- Displays summary stats with success rate percentage

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

### Filename Sanitization

- Inch symbol `"` → ` inch`
- Special characters (/, \, :, *, ?, <, >, |) removed
- Trademark symbols (™, ®) stripped
- Multiple spaces collapsed

### Usage

```bash
pip install requests beautifulsoup4 pillow
python scraper.py
```

**Output:**
- Images saved to `aquateak_products/` (deleted and recreated each run)
- Skip/error log saved to `scraper_log.txt` (deleted and recreated each run)
- Summary stats with success rate % printed to console and appended to log file

**Log File Format:**
```
SKU - Product Name: Reason for skip
SKU - Product Name: Reason for skip
...
[Summary with success rate %]
```

### Configuration

Settings in `scraper.py`:
- `BASE_URL` - Listing page URL
- `TOTAL_PAGES` - Pages to scrape
- `OUTPUT_DIR` - Save location
- `LOG_FILE` - Error/skip log file path
- `WHITE_THRESHOLD` - RGB threshold (235)
- `WHITE_PERCENTAGE` - Required white pixels (0.85)
- `SAMPLE_INTERVAL` - Sampling frequency (20px)
- `REQUEST_DELAY` - Request delay (0.5s)
- `CATEGORY_CONFIG` - Path to category JSON file

Categories and keywords configured in `category_prompts.json`

---

## Step 2: AI Image Generation (PLANNED)

### Workflow

For each scraped image:
1. Load original white-background image
2. Read category-specific prompt from `category_prompts.json`
3. Call Gemini API with combined prompt (base + category)
4. Generate 3-5 styled variants
5. **Remove Gemini watermark from bottom-right corner**
6. Save as: `SKU - Name - v1.jpg`, `SKU - Name - v2.jpg`, etc.

### Prompt Structure

**Base Prompt:** General instructions for all images (photorealistic, high-end aesthetic, sharp focus)

**Category Prompts:** Context-specific additions per category:
- **shower:** Wet tiles, water droplets, spa lighting
- **bench:** Entryway/bedroom, throw blanket, window light
- **chair:** Dining/living space, cushion, sophisticated interior
- **kitchen:** Marble countertop, fresh ingredients, bright lighting
- **outdoor:** Patio deck, greenery, golden hour sunlight
- **mat:** Overhead angle, floor perspective, water droplets
- *(etc.)*

Full prompt = `base_prompt + category_prompts[category]`

**API Parameters:** Aspect ratio (1:1) and output format (image/jpeg) specified via Gemini API parameters, not in prompt text.

All prompts and keywords configured in `category_prompts.json`

### Watermark Removal

**Recommended Approach: OpenCV Inpainting**
- Content-aware fill (like Photoshop's magic eraser)
- Intelligently fills masked region using surrounding pixels
- Library: `opencv-python`
- Method: Define mask for bottom-right corner → apply `cv2.inpaint()` with TELEA algorithm
- Most natural-looking results, no image area lost

**Alternative 1: Simple Crop**
- Remove bottom 60-80 pixels from image
- Fastest method, loses minimal image area
- Library: PIL/Pillow
- Trade-off: Slightly smaller final image

**Alternative 2: Logo Overlay**
- Cover watermark with your company logo
- Preserves full image, adds branding
- Library: PIL/Pillow
- Trade-off: Logo permanently visible on image

**Recommended:** Use OpenCV inpainting as post-processing step after each Gemini generation, before saving final variants.

### Watermark Removal

**Recommended: OpenCV Inpainting**
- Intelligent content-aware fill (like Photoshop magic eraser)
- Masks bottom-right corner where Gemini watermark appears
- Uses surrounding pixels to fill in naturally
- Install: `pip install opencv-python`
- Method: `cv2.inpaint()` with TELEA or NS algorithm

**Alternative 1: Simple Crop**
- Remove bottom 60-80 pixels from image
- Fastest method, loses some image area
- Use PIL: `img.crop((0, 0, width, height - 60))`

**Alternative 2: Logo Overlay**
- Cover watermark with your own logo
- Preserves full image, but adds branding layer
- Use PIL to paste logo in bottom-right corner

**Implementation Plan:**
Apply watermark removal as post-processing step after Gemini generates each variant, before saving final files.

### Expected Output

```
aquateak_products/
├── shower/
│   ├── originals/
│   │   └── 624 - 12 inch Aru...jpg
│   └── generated/
│       ├── 624 - 12 inch Aru... - v1.jpg
│       ├── 624 - 12 inch Aru... - v2.jpg
│       └── 624 - 12 inch Aru... - v3.jpg
```

---

## Step 3: Review & Deploy (PLANNED)

### Functionality

- View all variants side-by-side per product
- Compare original vs generated versions
- Select approved variants for deployment
- Batch export for website upload
- Quality control tracking

---

## File Structure

```
project/
├── scraper.py              # Scraping script (working)
├── category_prompts.json   # AI prompts per category (template)
├── README.md               # Documentation
├── scraper_log.txt         # Skip/error log (auto-generated)
└── aquateak_products/      # Output directory (auto-generated)
    ├── shower/
    ├── shelf/
    └── ...
```

---

## Technical Notes

- Rate limiting: 0.5s delay between requests
- Only downloads first/main product image (skips lifestyle shots)
- SKU numbers are unique per product
- Images stored at maximum resolution (1280x1280)
- All categories mutually exclusive (one category per product)