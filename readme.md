# Product Image AI Generation Pipeline

Complete automated workflow for transforming white-background product photography into professionally styled lifestyle imagery using AI image generation.

---

## Recent Updates (MAJOR REVISION - January 2026)

### Open/Closed Variant System (NEW)
- **Automatic detection** of openable products (cabinets, hampers, storage, organizers)
- **Doubles all variants** for openable products - generates both closed AND open states
- **Smart state modifiers** tell AI whether to show interior or exterior
- Categories flagged as `"openable": true` automatically get both states

### Enhanced Prompt System
- **4-layer structure:** Product name + Base prompt + Category prompt + State modifier (if openable)
- **Clearer shot type definitions:**
  - **Tight:** "ENTIRE product visible edge-to-edge" (was ambiguous before)
  - **Cropped:** "Show LESS THAN HALF of product" (was not distinct enough)
- **Lighting enforcement:** All base prompts now specify "bright studio lighting, clean throughout, no dark spots"

### Updated Naming Convention
**Non-openable products:** Same as before
```
624 - 0 Original.jpg
624 - 1 White refresh v1.jpg
624 - 3 Full room v1.jpg
```

**Openable products:** Now include state
```
307 - 0 Original.jpg
307 - 1 White refresh closed v1.jpg
307 - 1 White refresh open v1.jpg
307 - 3 Full room closed v1.jpg
307 - 3 Full room closed v2.jpg
307 - 3 Full room closed v3.jpg
307 - 3 Full room open v1.jpg
307 - 3 Full room open v2.jpg
307 - 3 Full room open v3.jpg
```

### Category-Specific Fixes
Based on generation feedback, addressed specific issues:
- Floor mats: "few subtle footprints acceptable"
- Hampers/storage: "positioned against wall" (placement consistency)
- Key hooks: "at least one hook empty" (natural look)
- Towel racks/items: "same color tone throughout" (visual coherence)
- Parasols: "parasol open" (functional display)
- Games: "single game setup" (prevents duplication)
- Bar stools: "close focus on one with others visible" (realistic framing)

**Philosophy:** Prompts describe settings generically. Let AI interpret naturally rather than over-constraining.

### Variant Count Updates
**Standard products:** 10 variants (unchanged)
- Room: 3, Tight: 3, Cropped: 2, White: 1, White-in-use: 1

**Openable products:** 20 variants (NEW - doubled)
- Room: 6 (3 closed + 3 open)
- Tight: 6 (3 closed + 3 open)
- Cropped: 4 (2 closed + 2 open)
- White: 2 (1 closed + 1 open)
- White-in-use: 2 (1 closed + 1 open)

### Cost Impact
**Test mode:** ~$11-12 (was ~$36)
- ~15 openable categories × 10 variants = 150 images
- ~15 standard categories × 5 variants = 75 images
- Total: 225 images × ~$0.05 = ~$11-12

**Production (350 products, ~50% openable): ~$260-280**
- 175 openable × 20 = 3,500 images
- 175 standard × 10 = 1,750 images
- Total: 5,250 images × ~$0.05 = **~$260-280** (TOP quality 4K)

---

## Setup Instructions

### 1. Install Dependencies
```bash
pip install requests beautifulsoup4 pillow tqdm
```

### 2. Create API Key File
1. Get your Gemini API key from: https://aistudio.google.com/apikey
2. Create a file named `apikey.txt` in the project directory
3. Paste your API key into the file (no spaces, no newlines, just the key)

**Important:** Add `apikey.txt` to your `.gitignore` to keep your key secure!

---

## Project Overview

### Purpose
Convert catalog product photos (white backgrounds) into multiple styled variations suitable for e-commerce, marketing, and social media. The system generates 10-20 AI variants per product (depending on whether product is openable) across 5 distinct shot types, maintaining brand consistency while adding contextual lifestyle appeal.

### Architecture
Three-phase pipeline with hierarchical organization:
1. **Scraper** - Extracts product images from live website, organized by native category structure
2. **Generator** - Creates AI-styled variants using Gemini Image Generation API with category-specific prompts
3. **Flattener** - Automatically creates flat dump alongside hierarchical structure for easy access (built into generator)

---

## Step 1: Product Image Scraper

### Core Functionality
The scraper performs intelligent extraction of product images from a live e-commerce site while maintaining the site's native organizational structure and implementing robust quality controls.

### White Background Validation
**Algorithm:**
1. Sample pixels around entire image perimeter at 20px intervals
2. Count pixels meeting threshold: R≥235, G≥235, B≥235
3. Calculate percentage of white pixels
4. Pass: ≥85% white pixels | Fail: <85% white pixels

**Why this approach:**
- Perimeter sampling catches gradients and shadows
- 235 threshold allows for studio lighting variations
- 85% requirement accommodates natural product shadows

### File Organization
**Structure created:**
```
aquateak_products/
├── Bathroom/
│   ├── Bathroom Furniture and Storage/
│   │   ├── Shower Benches/
│   │   │   ├── 624 - Teak Shower Bench.jpg
│   │   │   ├── 625 - Corner Shower Seat.jpg
│   │   ├── Shower Organizers and Caddies/
│   │       ├── 301 - Wall Mounted Caddy.jpg
```

**Filename format:** `{SKU} - {Product Name}.{ext}`
- Product name included to help AI understand product during generation
- Generator extracts name, passes to AI, but outputs use SKU only

---

## Step 2: AI Image Generation

### Open/Closed Variant System (NEW)

**Openable Categories (Auto-detected):**
- Bathroom: Shower Organizers and Caddies, Storage Bins and Trays, Storage, Waste Baskets and Hampers
- Indoor: Storage (all types), Waste Baskets and Hampers
- Outdoor: Storage Chests

**How it works:**
1. Each category has `"openable": true/false` flag in JSON
2. Generator detects flag and doubles all variants for openable products
3. Generates complete closed set, then complete open set
4. State modifiers tell AI to show interior (open) or exterior (closed)

**State Modifiers (Global):**
```json
"state_open": "Show product OPEN with interior visible and accessible."
"state_closed": "Show product CLOSED with only exterior visible."
```

These simple global instructions are appended to any openable product's prompt, regardless of shot type. Category prompts don't mention open/closed - they just describe the setting. State modifiers handle all open/closed logic.

### Shot Type System

#### 1. Room Shots (3 variants, or 6 if openable)
**Purpose:** Lifestyle inspiration and aspiration marketing
**Framing:** Pulled-back perspective showing significant room context
**Usage:** Homepage hero images, lifestyle galleries, social media

#### 2. Tight Shots (3 variants, or 6 if openable)
**Purpose:** Product detail pages and catalog listings
**Framing:** Edge-to-edge, complete product visible
**Usage:** Product detail pages, catalog grids, comparison views

**Clear definition:** "Frame product edge-to-edge showing complete item."

#### 3. Cropped Shots (2 variants, or 4 if openable)
**Purpose:** Premium material quality and craftsmanship showcase
**Framing:** Close-up detail, may crop product edges
**Usage:** Premium product descriptions, "quality" sections

**Clear definition:** "Zoom to show texture, materials, craftsmanship details."

#### 4. White Refresh (1 variant, or 2 if openable)
**Purpose:** Enhanced catalog shot with better lighting than original
**Framing:** Exact same product and angle as input, pure white background

#### 5. White In-Use (1 variant, or 2 if openable)
**Purpose:** Demonstrates product function on clean background
**Framing:** Same product angle, items placed in/on product

### Naming Convention

**Format:** `SKU - # Type [state] vX.jpg`

**Complete example for standard product (SKU 624, non-openable):**
```
624 - 0 Original.jpg
624 - 1 White refresh v1.jpg
624 - 2 White in use v1.jpg
624 - 3 Full room v1.jpg
624 - 3 Full room v2.jpg
624 - 3 Full room v3.jpg
624 - 4 Tight v1.jpg
624 - 4 Tight v2.jpg
624 - 4 Tight v3.jpg
624 - 5 Cropped v1.jpg
624 - 5 Cropped v2.jpg
```
**Total: 11 files (1 original + 10 variants)**

**Complete example for openable product (SKU 307, hamper):**
```
307 - 0 Original.jpg
307 - 1 White refresh closed v1.jpg
307 - 1 White refresh open v1.jpg
307 - 2 White in use closed v1.jpg
307 - 2 White in use open v1.jpg
307 - 3 Full room closed v1.jpg
307 - 3 Full room closed v2.jpg
307 - 3 Full room closed v3.jpg
307 - 3 Full room open v1.jpg
307 - 3 Full room open v2.jpg
307 - 3 Full room open v3.jpg
307 - 4 Tight closed v1.jpg
307 - 4 Tight closed v2.jpg
307 - 4 Tight closed v3.jpg
307 - 4 Tight open v1.jpg
307 - 4 Tight open v2.jpg
307 - 4 Tight open v3.jpg
307 - 5 Cropped closed v1.jpg
307 - 5 Cropped closed v2.jpg
307 - 5 Cropped open v1.jpg
307 - 5 Cropped open v2.jpg
```
**Total: 21 files (1 original + 20 variants)**

### Prompt System Architecture

**Four-component prompt structure (NEW):**
1. **Product name** - Extracted from input filename
2. **Base prompts** - One per shot type, defines shot characteristics
3. **Category prompts** - Specific to product category, defines setting details
4. **State modifiers** - Only for openable products (open/closed)

**How they combine:**
```
Non-openable (Room/Tight/Cropped): 
"Product: {name}. {Base} Setting: {Category}"

Non-openable (White/White-in-use): 
"Product: {name}. {Base}"

Openable (Room/Tight/Cropped): 
"Product: {name}. {Base} Setting: {Category} STATE: {State}"

Openable (White/White-in-use): 
"Product: {name}. {Base} STATE: {State}"
```

**Example for openable product - Hamper, Room Shot, Open State:**
```
Product: Laundry Hamper. Professional lifestyle photograph. PRODUCT MUST BE 
IDENTICAL to input image - exact same shape, size, construction. Show in 
natural room setting with pulled-back perspective. Few appropriate items nearby. 
Bright studio lighting, clean throughout. Setting: Bathroom, bedroom, or 
laundry room. Positioned against wall. Modern setting, bright lighting. 
STATE: Show product OPEN with interior visible and accessible.
```

Note: Category prompt just describes the setting. State modifier adds all open/closed logic.

### Prompt Philosophy & Key Directives

**Critical emphasis across all prompts:**

#### Product Identity (HIGHEST PRIORITY)
Every base prompt starts with: **"PRODUCT MUST BE IDENTICAL to input image - exact same shape, size, construction, logo"**

This prevents AI from modifying products (moving shelves, changing screws, altering construction).

#### Lighting Enforcement (NEW)
All base prompts now specify: **"Bright studio lighting, clean throughout, no dark spots"**

Eliminates moody/dark shots that were appearing previously.

#### Shot Type Clarity (UPDATED)
**Tight:** "Frame product edge-to-edge showing complete item."
- Clear and simple - entire product visible, minimal margins

**Cropped:** "Zoom to show texture, materials, craftsmanship details."
- Generic instruction - AI naturally zooms to interesting details
- No rigid quantitative rules that cause failures

#### White Shot Isolation (MAINTAINED)
White and white-in-use shots use ONLY base prompts + state (if applicable). Category prompts are skipped to prevent lifestyle bleed into white backgrounds.

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
  "image_size": "4K",
  
  "state_open": "Door or lid OPEN showing interior contents visible.",
  "state_closed": "Door or lid CLOSED, only exterior visible.",
  
  "categories": {
    "Top Category": {
      "Mid Category": {
        "Granular Category": {
          "prompt": "Category-specific scene description",
          "openable": true/false
        }
      }
    }
  }
}
```

**Cost structure (Gemini 3 Pro Image - TOP MODEL):**
- 4K resolution (4096px): ~$0.05 per image (exact pricing varies)
- Speed: 10-15 seconds per image
- Quality: Maximum - professional asset production

**Updated cost examples (using Gemini 3 Pro Image):**
- Test: 225 images × $0.05 = **~$11-12** (may vary based on exact pricing)
- Production (350 products, 50% openable): 5,250 images × $0.05 = **~$260-280**

**Note:** Using TOP model (Gemini 3 Pro Image Preview) for maximum quality at 4K resolution. Cost is higher but quality is unmatched.

**Runtime estimates (Gemini 3 Pro Image):**
- API call: ~10-15 seconds per image
- Delay between calls: 0.1 seconds
- Test mode: ~40-60 minutes (225 images)
- Production (350 products): ~15-22 hours (5,250 images)

---

## Category Structure & Prompts

### Openable Categories (10 total)

**Bathroom (4):**
- Shower Organizers and Caddies
- Storage Bins and Trays
- Storage
- Waste Baskets and Hampers

**Indoor (3):**
- Storage
- Waste Baskets and Hampers
- (Note: Tissue Boxes and Hangers - hangers are not openable, handled gracefully)

**Outdoor (1):**
- Storage Chests

### Non-Openable Categories (20 total)

**Bathroom (5):**
- Shower Benches, Floating Wall Shelves, Floor Mats, Towel Racks, Side Tables

**Indoor (8):**
- Entryway Benches, Key Holders, Coffee Tables, Shelving, Tissue Boxes and Hangers, Bar and Counter Stools, Countertop Accessories, Dining, Floor Mats

**Outdoor (9):**
- Benches, Daybeds, Dining Tables and Chairs, Games, Garden, Lighting, Lounge Chairs/Stools/Ottomans, Parasols, Sofas and Loveseats

---

## Project Workflow & Execution

**Complete pipeline:**

```bash
# 1. Scrape product catalog
python scraper.py
# Output: aquateak_products/ with ~350 products
# Time: ~30-60 minutes

# 2. Test generation (quality validation)
# TEST_MODE = True in generate_images.py (default)
python generate_images.py
# Output: 225 test images (includes open/closed for openable products)
# Time: ~40-60 minutes (Gemini 3 Pro Image is slower but TOP quality)
# Cost: ~$11-12

# 3. Review test outputs
# Verify prompt quality, open/closed states, lighting, shot type distinction

# 4. Production generation (full catalog)
# Set TEST_MODE = False in generate_images.py
python generate_images.py
# Output: ~5,250 images for 350 products
# Time: ~15-22 hours (Gemini 3 Pro Image - maximum quality)
# Cost: ~$260-280
```

---

## Project Statistics & Scale

### Input Scale
- 30 product categories (10 openable, 20 standard)
- ~350 unique products (varies with catalog)
- 1 image per product from scraper
- 1280x1280 resolution source images

### Output Scale (Production Mode)
- 11 files per standard product (1 original + 10 variants)
- 21 files per openable product (1 original + 20 variants)
- ~5,600 total files for 350 products (50% openable)
- ~11-12 GB total disk space
- Two complete folder structures (hierarchical + flat)

### Processing Scale
- API calls: 5,250 for 350 products (50% openable)
- Processing time: 15-22 hours for full catalog (Gemini 3 Pro Image)
- Cost: ~$260-280 at professional quality 4K
- Retry attempts: ~1-2% failure rate typical
- Quality: Maximum - 4096px native resolution

---

## Design Rationale & Key Decisions

### Why Open/Closed Variants?

**Problem:** Storage products, cabinets, hampers used in both states in real life. Single state was incomplete.

**Solution:** Auto-detect openable products, generate both states for ALL shot types.

**Benefits:**
- Shows product versatility (closed for aesthetics, open for function)
- Provides complete visual documentation
- Enables A/B testing of which state converts better
- Future-proofs catalog (have both, use as needed)

**Cost tradeoff:** 50% cost increase accepted for comprehensive coverage

### Why Global State Modifiers?

**Approach:** Single global instruction added to openable products
- `"Show product OPEN with interior visible and accessible."`
- `"Show product CLOSED with only exterior visible."`

**Why this works:**
- **Separation of concerns:** Category describes setting, state describes product state
- **No redundancy:** Don't repeat open/closed logic in 30 category prompts
- **Easy maintenance:** Change state instruction once, affects all categories
- **Simple and clear:** AI gets straightforward instruction without conditionals

**What changed:** Removed all "if closed... if open..." from category prompts. Category prompts now ONLY describe the setting/scene. State modifiers handle all open/closed logic globally.

### Why Simplified, Generic Prompts?

**Problem:** Over-specific prompts cause failures
- "Show exactly 2-3 items" → AI counts rigidly, creates unnatural scenes
- "Cropped at waist" → AI may fail if can't find waist in frame
- "LESS THAN HALF of product" → Quantitative rules = brittle

**Solution:** Generic, interpretable language
- "Few items nearby" → AI places natural amount
- "Close focus on one with others visible" → AI frames naturally
- "Zoom to show details" → AI finds interesting details

**Result:** More reliable generation, fewer failures, natural-looking results

**Philosophy:** Trust AI to interpret good photography. Describe what we want (bright, clean, detailed) not how to achieve it (exact counts, measurements, rigid rules).

---

## Dependencies & Requirements

### Python Packages
```
requests         # HTTP requests for scraping and API calls
beautifulsoup4   # HTML parsing for category extraction
pillow          # Image manipulation and format conversion
tqdm            # Progress bars with nested display
```

### API Requirements
- Gemini API key (free tier available)
- Internet connection for API calls
- No hard rate limit on free tier

### System Requirements
- Python 3.7+
- 15+ GB free disk space (for full catalog with open/closed)
- 2+ GB RAM
- Stable internet (hours-long API sessions)

---

## Version & Model Information

### Current Model
- Name: `gemini-3-pro-image-preview` (Nano Banana Pro)
- Status: Preview - TOP MODEL for professional image generation
- Provider: Google AI Studio
- Resolution: 4096px (4K native)
- Features: Advanced reasoning, 4K output, superior quality
- Cost: Higher cost accepted for maximum quality

### Known Limitations
- Free tier adds SynthID watermarks
- Rate limiting (generous but exists)
- Preview model may change behavior over time
- **Gemini 3 Pro Image may occasionally experience high load (503 errors)** - retry logic built into code handles this
- Slower generation time (10-15 seconds per image) accepted for maximum quality

---

This documentation provides complete understanding of the updated system architecture, including the new open/closed variant system and enhanced prompt clarity.