# Product Image AI Generation Pipeline

Complete automated workflow for transforming white-background product photography into professionally styled lifestyle imagery using AI image generation.

---

## Project Overview

### Purpose
Convert catalog product photos (white backgrounds) into multiple styled variations suitable for e-commerce, marketing, and social media. The system generates 10 AI variants per product across 5 distinct shot types, maintaining brand consistency while adding contextual lifestyle appeal.

### Architecture
Three-phase pipeline with hierarchical organization:
1. **Scraper** - Extracts product images from live website, organized by native category structure
2. **Generator** - Creates AI-styled variants using Gemini Image Generation API with category-specific prompts
3. **Flattener** - Automatically creates flat dump alongside hierarchical structure for easy access

### Key Design Decisions

**Why 5 shot types?**
- **Room shots** (3x) - Full lifestyle context for inspiration and aspiration marketing
- **Tight shots** (3x) - Product-focused while maintaining setting context for detail pages
- **Cropped shots** (2x) - Material quality and craftsmanship details for premium positioning
- **White refresh** (1x) - Enhanced original for clean catalog consistency
- **White in-use** (1x) - Demonstrates product usage while maintaining clean aesthetic

**Why dual folder output?**
- Hierarchical maintains organization for workflow and category management
- Flat dump provides immediate access for bulk operations, uploads, and reviews

**Why SKU-only naming in scraper?**
- Eliminates filename length issues and special character problems
- Enables consistent cross-referencing across systems
- Product names can change; SKUs are permanent identifiers
- Simplifies deduplication logic

---

## Step 1: Product Image Scraper

### Core Functionality

The scraper performs intelligent extraction of product images from a live e-commerce site while maintaining the site's native organizational structure and implementing robust quality controls.

### Category Structure Extraction

**How it works:**
1. Parses homepage navigation HTML to extract 3-level category hierarchy
2. Only processes top-level categories: Bathroom, Indoor, Outdoor
3. Ignores "Collections" and "Shop All" pages to avoid duplicates
4. Builds nested dictionary mapping: `Top → Mid → Granular → URL`

**Why this approach?**
- Site navigation reflects merchandising logic - we preserve this intentionally
- 3-level depth balances specificity with manageability
- Automatic extraction means structure updates with site changes
- Filtering out collection pages prevents massive duplicate downloads

**Category Coverage:**
- Bathroom: 9 granular categories
- Indoor: 11 granular categories  
- Outdoor: 10 granular categories
- Total: 30 distinct product types with unique use cases

### Scraping Logic

**Process per category:**
1. Request category page (handles pagination automatically)
2. Extract all product cards from page
3. Follow product links to detail pages
4. Extract SKU from product detail page HTML (searches for `<dt>SKU:</dt>`)
5. Extract largest available image URL (prioritizes 1280x1280 resolution)
6. Download image for white background validation
7. Keep or discard based on validation result

**Why visit product pages individually?**
- SKUs not available on category listing pages
- Largest image URLs only accessible from detail pages
- Product names more reliable on detail pages
- Enables extraction of additional metadata if needed

### White Background Validation

**Algorithm:**
1. Sample pixels around entire image perimeter at 20px intervals
2. Count pixels meeting threshold: R≥235, G≥235, B≥235
3. Calculate percentage of white pixels
4. Pass: ≥85% white pixels | Fail: <85% white pixels

**Why perimeter sampling?**
- Products with colored interiors still show white edges
- Catches gradients and shadows that full-image analysis might miss
- Computationally efficient (samples ~200 pixels vs millions)
- 20px interval balances accuracy with speed

**Why 235 threshold (not pure 255)?**
- Studio lighting creates slight variations (248, 252, etc.)
- Compression artifacts introduce minor color shifts
- 235 catches "effectively white" while excluding light grays
- Empirically tested to minimize false negatives

**Why 85% requirement?**
- Allows for product shadows and natural studio lighting effects
- Accommodates some artistic white background photography with subtle gradients
- Strict enough to exclude lifestyle shots with light backgrounds
- Prevents downloading pre-styled images that would confuse AI generation

### Global Deduplication

**System:**
- Maintains dictionary: `{SKU: category_path}`
- First occurrence: Download and record location
- Subsequent occurrences: Skip and log duplicate reference

**Why global (not per-category)?**
- Same products appear in multiple categories (e.g., storage items)
- Prevents wasted API calls, disk space, and processing time
- Maintains single source of truth for each product
- Log shows where duplicates would have appeared for merchandising insight

**Example:**
- Product SKU "123" first found in "Bathroom/Storage"
- Same SKU found later in "Living Room/Storage"  
- Second occurrence skipped, logged as duplicate with reference to original location

### File Organization

**Structure created:**
```
aquateak_products/
├── Bathroom/
│   ├── Bathroom Furniture and Storage/
│   │   ├── Shower Benches/
│   │   │   ├── 624.jpg
│   │   │   ├── 625.jpg
│   │   ├── Shower Organizers and Caddies/
│   │   │   ├── 301.jpg
│   ├── Bath Accessories/
│       ├── Floor Mats/
│       ├── Towel Racks/
```

**Filename format:** `{SKU}.jpg`
- Example: `624.jpg`, `1205.jpg`
- No product name, no versioning, no prefixes
- Always saved as .jpg regardless of source format (PNG converted)
- Folder names sanitized: `&` → `and`, special chars removed, `"` → ` inch`

**Why this structure?**
- Mirrors site organization for intuitive navigation
- Category-based prompts in AI generation require category context
- Enables category-level processing and reporting
- Preserves merchandising relationships

### Pagination Handling

**Logic:**
- Detects "next page" button in pagination HTML
- Continues scraping until no next button found
- Each page processed with REQUEST_DELAY between requests
- Accumulates products from all pages before processing

**Why this matters:**
- Some categories have 50+ products across multiple pages
- Without pagination, would miss majority of catalog
- Automatic detection handles varying page counts

### Output & Logging

**Console output:**
- Real-time progress bar showing total products processed
- Per-product status: ✓ downloaded, ⚠ skipped with reason
- Duplicate detection notifications with original location
- Summary statistics: total found, downloaded, skipped, duplicates

**Log file (scraper_log.txt):**
- Organized by error category (Background Too Dark, Duplicate, No Image URL, etc.)
- Per-product details: SKU, reason, specific values (e.g., "72.3% white pixels")
- Statistical summary with success rates
- Timestamped for correlation with run history

**Configuration:**
```python
BASE_URL = "https://aquateak.com"
WHITE_THRESHOLD = 235        # RGB min value for "white" classification
WHITE_PERCENTAGE = 0.85      # 85% of samples must pass threshold
SAMPLE_INTERVAL = 20         # Pixels between perimeter samples
REQUEST_DELAY = 0.5          # Seconds between requests (politeness)
```

---

## Step 2: AI Image Generation

### Architecture Overview

The generator traverses the scraped folder structure, applies category-specific prompts, and creates 5 distinct shot types per product using Google's Gemini Image Generation API. It maintains hierarchical organization while simultaneously creating a flat dump for convenience.

### Shot Type System

**Design philosophy:**
The 5 shot types serve distinct marketing purposes and together create a comprehensive visual story for each product.

#### 1. Room Shots (3 variants)
**Purpose:** Lifestyle inspiration and aspiration marketing
**Framing:** Pulled-back perspective showing significant room context
**Content:** Product in natural setting with surrounding furniture/decor visible
**Usage:** Homepage hero images, lifestyle galleries, social media, email marketing
**Why 3 variants:** Provides variety for A/B testing and seasonal rotations

**Technical approach:**
- Base prompt emphasizes "pulled-back perspective showing room context"
- Category prompts specify appropriate rooms and natural surroundings
- Multiple variants show different styling approaches for same product
- AI generates complementary furniture, appropriate lighting, realistic spatial relationships

#### 2. Tight Shots (3 variants)
**Purpose:** Product detail pages and catalog listings
**Framing:** Close framing with product filling most of frame, but complete product visible
**Content:** Full product shown with minimal but present environmental context
**Usage:** Product detail pages, catalog grids, comparison views
**Why 3 variants:** Different angles and lighting for comprehensive product view

**Technical approach:**
- Base prompt: "tight framing showing complete item...pulled in close but with full product visible"
- Maintains some setting context for realistic feel (not pure white background)
- Shows product scale accurately while maximizing visual real estate
- Balance between "lifestyle" and "catalog" aesthetics

#### 3. Cropped Shots (2 variants)
**Purpose:** Premium material quality and craftsmanship showcase
**Framing:** Extreme close-up showing approximately half or portion of product
**Content:** Texture details, wood grain, joinery, hardware, material quality
**Usage:** Premium product descriptions, "quality" sections, technical specification pages
**Why 2 variants:** Fewer needed as showing specific detail, not general product view

**Technical approach:**
- Base prompt: "close-up detail shot...zoomed in to show texture, materials, craftsmanship"
- May not show entire product - focuses on interesting details
- Highlights wood grain, corner joints, finish quality, hardware
- Creates "premium feel" through attention to craftsmanship

#### 4. White Refresh (1 variant)
**Purpose:** Enhanced catalog shot with better lighting than original
**Framing:** Product on pure white seamless background
**Content:** Just product, nothing else - enhanced version of original scrape
**Usage:** Primary catalog image, thumbnail grids, clean product listings
**Why 1 variant:** Catalog images need consistency, not variety

**Technical approach:**
- Base prompt: "studio product photograph...pure white seamless background"
- References original white background image but generates enhanced lighting
- "Premium commercial photography quality" with "soft shadows"
- Maintains original product perspective while improving lighting and shadows
- More professional than typical scraped white background shots

#### 5. White In-Use (1 variant)
**Purpose:** Demonstrates product function on clean background
**Framing:** Product on white background but styled with appropriate items
**Content:** Product shown in use - towels on hooks, items in baskets, cushions on furniture
**Usage:** Feature callouts, "how to use" sections, clean demonstration imagery
**Why 1 variant:** Functional demonstration needs clarity, not artistic variety

**Technical approach:**
- Base prompt: "studio photograph...white background, showing product in natural use"
- References original product but adds contextual items: "towels on hooks, items in baskets"
- Maintains studio aesthetic (no room context) while showing product purpose
- Generic styling for accessory items (not branded products)

### Naming Convention

**Format:** `SKU - type vX.jpg`

**Complete example for SKU 624:**
```
624 - Original.jpg       → Copy of original scraped image
624 - room v1.jpg        → Room lifestyle shot, variant 1
624 - room v2.jpg        → Room lifestyle shot, variant 2
624 - room v3.jpg        → Room lifestyle shot, variant 3
624 - tight v1.jpg       → Tight product shot, variant 1
624 - tight v2.jpg       → Tight product shot, variant 2
624 - tight v3.jpg       → Tight product shot, variant 3
624 - cropped v1.jpg     → Cropped detail shot, variant 1
624 - cropped v2.jpg     → Cropped detail shot, variant 2
624 - white v1.jpg       → Refreshed white background
624 - white-in-use v1.jpg → White background with product in use
```

**Design rationale:**
- SKU first enables alphabetical sorting by product
- Type in middle enables filtering/grouping by shot type
- Version at end follows natural variant progression
- Spaces for readability, hyphens to separate type descriptors
- "Original" vs "v1" distinguishes source from generated content
- Consistent pattern enables programmatic filename parsing

### Prompt System Architecture

**Two-tier prompt structure:**
1. **Base prompts** (5 total) - One per shot type, defines shot characteristics
2. **Category prompts** (30 total) - Specific to product category, defines setting details

**How they combine:**
```
Final API Prompt = Base Prompt + Category Prompt
```

**Example for Shower Bench, Room Shot:**
```
Base: "Professional lifestyle photograph showing the item from the provided 
image in its natural setting with pulled-back perspective showing room context. 
MAINTAIN ACCURATE PRODUCT SCALE..."

Category: "Spa-like shower setting with wet tile surfaces and ambient lighting. 
Product shown with wet surfaces, minimal bath products nearby (1-2 bottles, 
maybe a towel). NO steam, NO running water..."

Combined: Sent to API as single prompt with both elements
```

### Prompt Philosophy & Key Directives

**Critical emphasis across all prompts:**

#### Scale Accuracy
**Problem identified:** AI tends to missize products when no context clues present in white background reference
**Solution:** Every base prompt includes "MAINTAIN ACCURATE PRODUCT SCALE"
**Implementation:** Prompts specify product should be "sized realistically relative to surroundings"
**Why critical:** Wrong scale destroys believability (e.g., bar stool sized like dining chair)

#### Clutter Reduction
**Problem identified:** Initial generations had excessive accessories (10 bottles, 3 sponges on single bench)
**Solution:** Specific counts in category prompts: "1-2 bottles", "2-3 items", "2-4 pieces"
**Implementation:** Changed from generic "products around" to exact counts
**Why critical:** Over-cluttered images feel staged and unrealistic, distract from main product

#### Location Flexibility
**Problem identified:** Rigid room specifications caused unnatural placements (dog bowls on dining table, hangers on nightstand)
**Solution:** Multiple location options in prompts: "bathroom, bedroom, spa locker room, or laundry room"
**Implementation:** OR statements and flexible language: "can show", "maybe"
**Why critical:** Products used in multiple contexts need varied settings for natural feel

#### Lighting Balance
**Problem identified:** Early results had "over-the-top intense fancy" lighting
**Solution:** Changed descriptor from "professional" to "chill luxury" with "balanced ambient lighting"
**Implementation:** Explicitly state "not over-the-top" in prompts
**Why critical:** Excessive dramatic lighting feels unrealistic and distracts from product

#### Logo Handling
**Problem identified:** AI sometimes replicated main product logo onto accessory items (shampoo bottles copying bench brand)
**Solution:** "Replicate main product logo EXACTLY as shown, generic styling for accessories"
**Implementation:** Split instruction - exact replication for main product, generic for surroundings
**Why critical:** Brand consistency on main product, but branded accessories feel like product placement

#### Wet Surfaces (Bathroom Products)
**Problem identified:** Initial bathroom shots had excessive steam and running water looking fake
**Solution:** "Wet surfaces YES, steam NO, running water NO"
**Implementation:** Explicit negatives in prompts with positive alternative
**Why critical:** Wet surfaces show real use; steam/running water looks artificial and generated

### Category-Specific Customizations

**Examples demonstrating prompt variety:**

**Shower Benches:**
```
"Spa-like shower setting with wet tile surfaces and ambient lighting. 
Product shown with wet surfaces, minimal bath products nearby (1-2 bottles, 
maybe a towel). NO steam, NO running water, NO logo copies on bottles. 
Natural bathroom atmosphere."
```
- Specific count: "1-2 bottles" prevents clutter
- Explicit negatives: prevents common AI mistakes
- "Spa-like" sets upscale tone matching product positioning

**Bar & Counter Stools:**
```
"Kitchen island or breakfast bar with countertop visible. Show close-up 
of one stool with others visible at bar in background. Pendant lighting 
overhead, contemporary kitchen."
```
- "Close-up of one stool with others visible" solves multiple-item framing
- Prevents AI from equally showing all stools (which looks unnatural)
- "Others visible at bar" maintains context of multiple-seating use case

**Floor Mats:**
```
"Bathroom floor in front of shower or bath with wet surface nearby. 
Clean tile or stone flooring, natural lighting. Maybe slippers on or 
near mat. Few subtle footprints acceptable, not excessive."
```
- "In front of shower or bath" (not "and") gives location flexibility
- "Few subtle footprints...not excessive" learned from over-footprinted early versions
- "Maybe slippers" adds realistic detail without requirement

**Hampers:**
```
"Bathroom, bedroom, spa locker room, or laundry room setting. Show product 
both open and closed in different variants when applicable. Folded linens 
or items nearby, modern flooring, ambient lighting."
```
- Multiple location options reflect real-world usage
- "Show both open and closed" creates variety across variants
- Recognizes hampers function in multiple home contexts

**Games (Corn Toss):**
```
"Set up on lawn or patio with outdoor area in background. Natural daylight, 
backyard setting. Single game setup, not multiples side by side."
```
- "Single game setup" prevents AI from generating two boards (common mistake)
- Learned from early results showing duplicate setups

### API Technical Details

**Request structure sent to Gemini:**
```python
{
  "contents": [{
    "parts": [
      {"text": "[Combined Base + Category Prompt]"},
      {"inline_data": {
        "mime_type": "image/jpeg",
        "data": "[base64 encoded original image]"
      }}
    ]
  }],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"],
    "imageConfig": {
      "aspectRatio": "1:1",
      "imageSize": "4K"
    }
  }
}
```

**Why this structure:**
- Text prompt + reference image enables "style transfer with direction"
- Base64 encoding required by API (images not passed as URLs)
- aspectRatio: "1:1" maintains square format for versatility (web, social, print)
- imageSize: "4K" (4096px) provides print-quality output
- responseModalities: ["TEXT", "IMAGE"] allows API to return both (we only use image)

**Model selection:**
- Both test and production use `gemini-3-pro-image-preview`
- Consistent quality across testing and final output
- Pro model supports "imageSize" parameter (Flash model does not)
- Preview designation indicates evolving capabilities

**Output handling:**
- API returns base64 encoded image in response JSON
- Decoded to PIL Image object
- Saved as JPEG at 95% quality (balances quality and file size)
- Original file format (PNG from scrape) converted to JPG for consistency

### Variant Generation Logic

**Per product, per shot type:**
1. Load original white background image
2. Construct prompt (base + category)
3. Encode image to base64
4. Call Gemini API with prompt + image + config
5. Receive generated image (base64)
6. Decode and save as JPEG
7. Delay 0.1 seconds (rate limiting politeness)
8. Repeat for next variant

**Error handling:**
- 3 retry attempts per variant with exponential backoff
- Rate limit (429) errors trigger progressive delays: 10s, 20s, 40s
- Other HTTP errors fail immediately with logging
- Failed variants logged but don't stop processing
- Progress bars update on both success and failure

**Why 3 retries:**
- Transient network issues common over hours-long runs
- Rate limits sometimes temporary (burst capacity recovery)
- 3 attempts with backoff usually succeeds without excessive wait
- Logs permanent failures for manual review

### Test Mode vs Production Mode

**Test Mode (TEST_MODE = True):**
- Processes 1 product per category (30 products total)
- Generates 1 of each shot type (5 variants per product)
- Total output: 30 × 5 = 150 images
- Cost: ~$36 (150 × $0.24)
- Purpose: Validate prompts, review quality, test changes

**Production Mode (TEST_MODE = False):**
- Processes all products in all categories
- Generates full variant counts (10 variants per product)
- Total output depends on product count (e.g., 350 products = 3,500 images)
- Cost: Product count × 10 × $0.24
- Purpose: Full catalog generation for deployment

**Why this split:**
- Test mode enables rapid iteration on prompts without cost
- 30 products samples all categories for quality review
- 1 variant per type shows prompt effectiveness without redundancy
- Production mode runs overnight for full catalog

### Folder Output System

**Dual output structure:**

**1. Hierarchical (generated_images/):**
```
generated_images/
└── Bathroom/
    └── Bathroom Furniture and Storage/
        └── Shower Benches/
            ├── 624/
            │   ├── 624 - Original.jpg
            │   ├── 624 - room v1.jpg
            │   ├── 624 - room v2.jpg
            │   ├── 624 - room v3.jpg
            │   ├── 624 - tight v1.jpg
            │   ├── 624 - tight v2.jpg
            │   ├── 624 - tight v3.jpg
            │   ├── 624 - cropped v1.jpg
            │   ├── 624 - cropped v2.jpg
            │   ├── 624 - white v1.jpg
            │   └── 624 - white-in-use v1.jpg
            └── 625/
                └── [same structure]
```

**Purpose:**
- Maintains category context for workflow management
- Enables category-level reporting and review
- Mirrors scraper structure for consistency
- Product subfolders group all variants per SKU
- Preserves organizational logic for team collaboration

**2. Flat Dump (all_generated/):**
```
all_generated/
├── 624 - Original.jpg
├── 624 - room v1.jpg
├── 624 - room v2.jpg
├── 624 - room v3.jpg
├── 625 - Original.jpg
├── 625 - room v1.jpg
└── ... (all products, all variants)
```

**Purpose:**
- Immediate access to all images without navigation
- Easy bulk operations (upload, backup, review)
- Simple folder sharing and transfer
- No hierarchy to navigate for quick preview

**Flattening logic:**
- Runs automatically after generation completes
- Recursively walks generated_images/ tree
- Copies all image files to single folder
- Handles duplicate filenames by appending _1, _2, etc.
- Non-destructive: hierarchical structure remains intact

**Why both:**
- Different use cases require different structures
- Hierarchical for workflow, flat for operations
- Cost: minimal (disk space, copy operation <1 min)
- Benefit: eliminates "which folder should I use?" decisions

### Configuration & Costs

**Configuration (category_prompts.json):**
```json
{
  "room_variants_per_image": 3,
  "tight_variants_per_image": 3,
  "cropped_variants_per_image": 2,
  "white_variants_per_image": 1,
  "white_in_use_variants_per_image": 1,
  "aspect_ratio": "1:1",
  "image_size": "4K"
}
```

**Cost structure (Gemini API pricing):**
- 1K resolution (1024px): $0.134 per image
- 2K resolution (2048px): $0.18 per image
- 4K resolution (4096px): $0.24 per image

**Cost examples at 4K:**
- Test: 150 images × $0.24 = $36
- 100 products: 1,000 images × $0.24 = $240
- 350 products: 3,500 images × $0.24 = $840

**Runtime estimates:**
- API call: ~2-5 seconds per image
- Delay between calls: 0.1 seconds
- Test mode: ~15-30 minutes
- 350 products: ~3-6 hours

**Watermarks:**
- Google adds "Gemini sparkle" logo to all generated images (bottom-right)
- Free-tier API policy (not present in paid enterprise tier)
- Removable via OpenCV inpainting if needed (not currently implemented)

---

## File Formats & Technical Specifications

### Image Specifications

**Scraper output:**
- Format: JPEG (converted from PNG if necessary)
- Resolution: 1280x1280 (maximum available from source site)
- Quality: Source quality preserved
- Aspect ratio: Variable (products photographed as-is)
- Color space: RGB

**Generator output:**
- Format: JPEG (all variants)
- Resolution: 4096x4096 at 4K setting
- Quality: 95% JPEG quality
- Aspect ratio: 1:1 square (configurable)
- Color space: RGB
- File sizes: ~800KB-2MB per image

### Naming Standards

**Scraper:**
- Pattern: `{SKU}.jpg`
- Example: `624.jpg`
- No spaces, no special characters
- Always lowercase extension

**Generator:**
- Pattern: `{SKU} - {type} v{number}.jpg`
- Example: `624 - room v1.jpg`
- Special case: `{SKU} - Original.jpg` (no version number)
- Spaces separate major components
- Hyphens within type descriptors: `white-in-use`

**Folder names:**
- Source: Site navigation text
- Sanitization: `&` → `and`, special chars removed, `"` → ` inch`
- Example: `Bathroom Furniture and Storage`
- Spaces preserved for readability
- Case preserved from source

### File Organization Logic

**Hierarchy principle:**
```
Top Category (3 types)
└── Mid Category (varies)
    └── Granular Category (30 total)
        └── Product (by SKU)
            └── Variants (11 files)
```

**Why this depth:**
- Top level: Major home areas (Bathroom, Indoor, Outdoor)
- Mid level: Functional groupings (Furniture, Accessories, etc.)
- Granular level: Specific product types (Shower Benches, Bar Stools)
- Product level: Individual SKUs (keeps variants together)

**Deduplication locations:**
- Scraper: Global dictionary prevents same SKU downloading twice
- Generator: Processes each scraped folder independently (no duplicates exist)
- Flattener: Handles filename collisions with suffix numbering

---

## Project Workflow & Execution

### Complete Pipeline Execution

**Step-by-step:**

```bash
# 1. Scrape product catalog
python scraper.py
# Output: aquateak_products/ with ~350 products organized in 30 categories
# Time: ~30-60 minutes depending on product count
# Logs: scraper_log.txt

# 2. Test generation (quality validation)
# Set TEST_MODE = True in generate_images.py
python generate_images.py
# Output: generated_images/ and all_generated/ with 150 test images
# Time: ~15-30 minutes
# Cost: ~$36
# Logs: generation_log.txt

# 3. Review test outputs
# Check both folder structures
# Verify prompt quality, scale accuracy, appropriate styling
# Adjust category_prompts.json if needed

# 4. Production generation (full catalog)
# Set TEST_MODE = False in generate_images.py
python generate_images.py
# Output: Both folders with all products, all variants
# Time: ~3-6 hours for 350 products
# Cost: ~$840 for 350 products
# Logs: generation_log.txt
```

### What Happens During Scraping

1. **Initialization:**
   - Clears any existing output folder (fresh start)
   - Clears log file
   - Initializes global deduplication dictionary

2. **Structure extraction:**
   - Requests homepage
   - Parses navigation HTML
   - Builds category structure dictionary
   - Creates folder hierarchy on disk

3. **Per category:**
   - Requests category page
   - Extracts all product cards
   - Checks pagination for more pages
   - Repeats until no next page

4. **Per product:**
   - Follows product URL
   - Extracts SKU from detail page
   - Checks global deduplication dictionary
   - If new: extracts image URL, downloads, validates, saves
   - If duplicate: logs and skips
   - Delays 0.5 seconds before next request

5. **Completion:**
   - Writes organized log file
   - Displays summary statistics
   - Preserves folder structure for generator

### What Happens During Generation

1. **Initialization:**
   - Loads category_prompts.json
   - Determines variant counts (test: 1 each, production: configured counts)
   - Counts total images to generate for progress tracking
   - Clears existing output folders (fresh start)

2. **Structure traversal:**
   - Walks scraper output hierarchy: Top → Mid → Granular
   - For each granular category, loads appropriate prompt
   - In test mode: processes only first product
   - In production mode: processes all products

3. **Per product:**
   - Copies original image as "{SKU} - Original.jpg"
   - For each of 5 shot types:
     - Constructs prompt (base + category)
     - For each variant (1 in test, configured in production):
       - Encodes original image to base64
       - Calls Gemini API with prompt + image
       - Decodes response
       - Saves as JPEG with appropriate filename
       - Delays 0.1 seconds
   - Updates progress bars
   - Logs any errors

4. **Flattening:**
   - After all generation completes
   - Walks generated_images/ hierarchy
   - Copies all images to all_generated/
   - Handles filename conflicts with numeric suffixes
   - Preserves original hierarchical structure

5. **Completion:**
   - Displays summary statistics
   - Notes both output locations
   - Logs final report to generation_log.txt

### Configuration Files

**scraper.py settings:**
```python
BASE_URL = "https://aquateak.com"
WHITE_THRESHOLD = 235        # Min RGB for white pixel classification
WHITE_PERCENTAGE = 0.85      # Required white pixel percentage
SAMPLE_INTERVAL = 20         # Perimeter sampling density
REQUEST_DELAY = 0.5          # Politeness delay between requests
```

**generate_images.py settings:**
```python
GEMINI_API_KEY = "..."       # Required: API key from aistudio.google.com
TEST_MODE = True/False       # Controls processing scope
REQUEST_DELAY = 0.1          # Minimal delay for speed
GEMINI_MODEL = "gemini-3-pro-image-preview"
```

**category_prompts.json structure:**
```json
{
  "room_variants_per_image": 3,
  "tight_variants_per_image": 3,
  "cropped_variants_per_image": 2,
  "white_variants_per_image": 1,
  "white_in_use_variants_per_image": 1,
  "aspect_ratio": "1:1",
  "image_size": "4K",
  
  "base_prompt_room": "...",
  "base_prompt_tight": "...",
  "base_prompt_cropped": "...",
  "base_prompt_white": "...",
  "base_prompt_white-in-use": "...",
  
  "categories": {
    "Top Category": {
      "Mid Category": {
        "Granular Category": {
          "prompt": "Category-specific scene description"
        }
      }
    }
  }
}
```

---

## Design Rationale & Key Decisions

### Why This Prompt Structure?

**Two-tier system (base + category) instead of single prompts:**
- **Consistency:** Base prompts ensure all room shots feel cohesive, all tight shots have similar framing
- **Flexibility:** Category prompts customize scene without rewriting fundamentals
- **Maintainability:** Change all room shots by editing one base prompt
- **Scalability:** Add new categories without redefining shot type characteristics

### Why These Specific Variant Counts?

**Room: 3 variants**
- Marketing needs variety for campaigns, A/B testing, seasonal rotations
- Different styling approaches show product versatility
- Three provides choice without overwhelming options

**Tight: 3 variants**  
- Product detail pages benefit from multiple angles
- Shows product from different perspectives
- Enough for carousel/gallery displays

**Cropped: 2 variants**
- Detail shots more uniform (less variation in grain/texture)
- Two angles sufficient to show quality
- Fewer needed as not used as primary product images

**White: 1 variant**
- Catalog consistency requires uniform presentation
- Not meant to vary - single "best" version needed
- Replaces original as primary SKU image

**White in-use: 1 variant**
- Functional demonstration has single clear purpose
- Variety would confuse the "how to use" message
- One clear example sufficient

### Why Square Aspect Ratio?

**1:1 chosen for maximum versatility:**
- **Web:** Works in grid layouts without cropping
- **Social:** Instagram, Facebook, Pinterest native format
- **Print:** Easily crops to any orientation
- **Thumbnails:** No awkward cropping in listing views
- **Responsive:** Scales cleanly at any size

**Alternative (16:9) rejected because:**
- Horizontal products waste vertical space
- Tall products (shelves, benches) need vertical format
- Social media prefers square or vertical
- Grid layouts more complex with rectangles

### Why 4K Resolution?

**4096px chosen for future-proofing:**
- **Print quality:** 300 DPI at 13.6" wide (poster size)
- **Retina displays:** 2x pixel density = 2048px effective
- **Zoom capability:** Users can zoom without pixelation
- **Downsampling:** Easy to resize down, impossible to upsize
- **Archive quality:** Preserves original generation detail

**Cost tradeoff accepted:**
- $0.24 vs $0.134 (1K) = $0.106 premium per image
- $37 extra for 350 products (1K: $469, 4K: $840)
- Worth it for print capability and future needs

### Why Global Deduplication Instead of Per-Category?

**Global tracking chosen because:**
- Same products legitimately appear in multiple categories
- First categorization preserved (likely more accurate)
- Prevents wasted scraping time and disk space
- Log shows cross-category product relationships
- Single source of truth for each SKU

**Alternative (allow duplicates) rejected:**
- Wastes API calls generating same product multiple times
- Creates confusion about which version is canonical
- Inflates storage requirements
- Complicates product count tracking

### Why Copy Original Into Generated Structure?

**Including "Original.jpg" in each product folder:**
- Keeps all versions of product together
- Enables side-by-side comparison during review
- Provides reference for scale/color accuracy checking
- Self-contained folders can be shared independently
- No need to reference back to scraper folder

**Only minimal cost:**
- Disk space negligible (already downloaded)
- Copy operation fast (<1 second for all products)
- Organizational benefit outweighs small duplication

### Why Automatic Flattening vs Manual?

**Auto-flatten after generation:**
- Eliminates extra manual step
- Ensures both structures always in sync
- No risk of forgetting to flatten
- Immediate access to flat structure for review

**Cost: Negligible (~30 seconds copy time)**
**Benefit: Dual-structure convenience without workflow complexity**

---

## Category Structure & Prompts

### Complete Category List (30 Total)

**Bathroom (9 categories):**
1. Shower Benches
2. Shower Organizers and Caddies  
3. Floating Wall Shelves
4. Storage Bins and Trays
5. Storage
6. Floor Mats
7. Waste Baskets and Hampers
8. Towel Racks
9. Side Tables

**Indoor (11 categories):**
1. Entryway Benches
2. Key Holders
3. Coffee Tables
4. Shelving
5. Storage
6. Tissue Boxes and Hangers
7. Waste Baskets and Hampers
8. Bar and Counter Stools
9. Countertop Accessories
10. Dining
11. Floor Mats

**Outdoor (10 categories):**
1. Benches
2. Daybeds
3. Dining Tables and Chairs
4. Games
5. Garden
6. Lighting
7. Lounge Chairs, Stools and Ottomans
8. Parasols
9. Sofas and Loveseats
10. Storage Chests

### Prompt Customization Examples

**Specific learnings embedded in prompts:**

**Shower Benches:** "NO steam, NO running water, NO logo copies on bottles"
- Early versions had excessive steam (looked artificial)
- Running water appeared fake/CGI
- AI copied bench brand onto shampoo bottles (unintended)

**Floor Mats:** "Few subtle footprints acceptable, not excessive"
- Initial results had 20+ footprints (looked ridiculous)
- Changed to "few subtle" for realistic use indication

**Hampers:** "Show product both open and closed in different variants"
- Hampers used both ways in real life
- Variants now show functional variety

**Bar Stools:** "Show close-up of one stool with others visible at bar in background"
- Original: AI tried to show all stools equally (unnatural framing)
- Fixed: Focus on one, context from others

**Games:** "Single game setup, not multiples side by side"
- AI generated two corn toss boards side-by-side (never happens)
- Explicit "single" fixes unnatural duplication

**Key Holders:** "Mounted near front door, in entryway, or bathroom as towel hook"
- Recognized hooks serve multiple purposes
- Variety shows real-world versatility

---

## Technical Implementation Details

### API Request Flow

1. **Image preparation:**
   - Load original JPEG from disk
   - Read as binary data
   - Encode to base64 string
   - Store in memory for API call

2. **Request construction:**
   - Build JSON payload with prompt + image
   - Add generation config (aspect ratio, size)
   - Set headers (API key, content type)
   - Set 60-second timeout

3. **API call:**
   - POST to Gemini API endpoint
   - Wait for response (typically 2-5 seconds)
   - Handle HTTP errors with retries
   - Parse JSON response

4. **Response processing:**
   - Extract base64 image data from response
   - Decode base64 to binary
   - Create PIL Image object
   - Save as JPEG with 95% quality

5. **Error handling:**
   - 429 (rate limit): Exponential backoff retry
   - 4xx errors: Log and skip variant
   - 5xx errors: Retry up to 3 times
   - Network errors: Retry with delay

### Progress Tracking System

**Two-level progress bars:**
1. **Overall progress:** Total variants across all products
2. **Category progress:** Variants for current category

**Why two levels:**
- Overall shows project completion
- Category shows current task progress
- Nested bars provide context without overwhelming
- tqdm library manages cursor positioning

**Progress calculation:**
- Pre-counts all products to determine total variants
- Updates on every variant (success or failure)
- Shows percentage, count, and estimated time remaining

### Logging Strategy

**Console output:**
- Real-time progress bars
- Per-product status messages (✓ success, ⚠ skip)
- Category headers for context
- Final summary with statistics

**Log files:**
- Organized by error category (not chronological)
- Includes specific details (SKU, white percentage, error message)
- Summary statistics at end
- Timestamp for correlation

**Why organized by category:**
- Patterns more visible (e.g., "all floor mats too dark")
- Actionable insights easier to extract
- Similar issues grouped for bulk resolution

### Memory Management

**Image handling:**
- Load original once per product (not per variant)
- Decode API response immediately to PIL Image
- Save to disk and release from memory
- Never hold multiple generated images in memory

**Why this matters:**
- 4K images are ~2MB each
- 10 variants × 350 products = 3,500 images
- Holding in memory would require 7GB
- Disk I/O fast enough that memory caching unnecessary

### File I/O Optimization

**Scraper:**
- Streaming download (not full buffer)
- Write directly to final location
- No temporary files

**Generator:**
- Original copied once before variant generation
- Variants saved directly to final location
- No temporary folders

**Flattener:**
- Uses shutil.copy2 (preserves metadata)
- Walks tree once
- Copies all files in single pass

---

## Project Statistics & Scale

### Input Scale
- 30 product categories
- ~350 unique products (varies with catalog)
- 1 image per product from scraper
- 1280x1280 resolution source images

### Output Scale (Production Mode)
- 11 files per product (1 original + 10 variants)
- ~3,850 total files for 350 products
- ~7-8 GB total disk space
- Two complete folder structures (hierarchical + flat)

### Processing Scale
- API calls: 3,500 for 350 products
- Processing time: 3-6 hours for full catalog
- Cost: ~$840 at 4K resolution
- Retry attempts: ~1-2% failure rate typical

### Performance Metrics
- Scraping: ~1-2 products per second
- Generation: ~2-3 variants per minute (API limited)
- Flattening: ~1,000 files per second
- Total pipeline: ~4-7 hours for complete refresh

---

## Dependencies & Requirements

### Python Packages
```
requests         # HTTP requests for scraping and API calls
beautifulsoup4   # HTML parsing for category extraction
pillow          # Image manipulation and format conversion
tqdm            # Progress bars with nested display
opencv-python   # (Optional) For watermark removal if implemented
```

### API Requirements
- Gemini API key (free tier available)
- Internet connection for API calls
- No rate limit on free tier (reasonable use expected)

### System Requirements
- Python 3.7+ (f-strings, type hints)
- 10+ GB free disk space (for full catalog)
- 2+ GB RAM (for image processing)
- Stable internet (hours-long API sessions)

---

## Version & Model Information

### Current Model
- Name: `gemini-3-pro-image-preview`
- Status: Preview (evolving capabilities)
- Provider: Google AI Studio
- Features: Image generation from prompt + reference image
- Limitations: Watermarks on free tier, rate limiting

### API Endpoint
```
https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent
```

### Model Capabilities
- Input: Text prompt + reference image (base64)
- Output: Generated image (base64)
- Max resolution: 4096x4096 (4K)
- Aspect ratios: Square, portrait, landscape variants
- Response time: 2-5 seconds typical

### Known Limitations
- Free tier adds watermarks (bottom-right corner)
- Rate limiting (generous but exists)
- Preview model may change behavior over time
- No guarantee of output consistency across months
- Cannot remove watermarks via API parameter

---

This documentation provides complete understanding of the system architecture, design decisions, and implementation details for the AI product image generation pipeline.