# Product Image AI Generation Pipeline

Complete automated workflow for transforming white-background product photography into professionally styled lifestyle imagery using AI image generation.

---

## Recent Updates (January 2026)

### Parallel Processing System (NEW)
- **Concurrent API calls** using ThreadPoolExecutor for ~5x speed improvement
- **Configurable parallelism** via `max_parallel_requests` in JSON config
- **Thread-safe logging** prevents race conditions during parallel execution
- **Automatic rate limit handling** with exponential backoff (10s → 20s → 40s)
- **Per-variant retry logic** - individual failures don't block other variants

### Open/Closed Variant System
- **Automatic detection** of openable products (cabinets, hampers, storage, organizers)
- **Doubles all variants** for openable products - generates both closed AND open states
- **Smart state modifiers** tell AI whether to show interior or exterior
- Categories flagged as `"openable": true` automatically get both states

### Enhanced Prompt System
- **4-layer structure:** Product name + Base prompt + Category prompt + State modifier (if openable)
- **Shot type definitions:**
  - **Tight:** "ENTIRE product visible edge-to-edge"
  - **Cropped:** "Zoom to show texture, materials, craftsmanship details"
- **Lighting enforcement:** All base prompts specify "bright studio lighting, clean throughout"

### Naming Convention
**Non-openable products:**
```
624 - 0 Original.jpg
624 - 1 White refresh v1.jpg
624 - 3 Full room v1.jpg
```

**Openable products (include state):**
```
307 - 0 Original.jpg
307 - 1 White refresh closed v1.jpg
307 - 1 White refresh open v1.jpg
307 - 3 Full room closed v1.jpg
307 - 3 Full room open v1.jpg
```

---

## Project Overview

### Purpose
Converts catalog product photos (white backgrounds) into multiple styled variations suitable for e-commerce, marketing, and social media. The system generates 10-20 AI variants per product (depending on whether product is openable) across 5 distinct shot types, maintaining brand consistency while adding contextual lifestyle appeal.

### Architecture
Three-phase pipeline with hierarchical organization:
1. **Scraper** - Extracts product images from live website, organized by native category structure
2. **Generator** - Creates AI-styled variants using Gemini Image Generation API with category-specific prompts and parallel processing
3. **Flattener** - Automatically creates flat dump alongside hierarchical structure (built into generator)

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

**Rationale:**
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

### Parallel Processing Architecture

**Implementation:** ThreadPoolExecutor manages concurrent API calls
- All variants for a product are queued as independent tasks
- Worker threads execute API calls simultaneously
- Results collected via `as_completed()` for immediate progress updates

**Thread Safety:**
- Logging protected by `threading.Lock()` to prevent interleaved output
- Each task is fully independent (no shared mutable state)
- Progress bars updated atomically

**Rate Limit Handling:**
- 429 responses trigger exponential backoff: 10s → 20s → 40s
- Retries are per-variant, not global
- Failed variants logged but don't block other variants
- 3 retry attempts per variant before marking as failed

**Performance Impact:**
- Sequential: ~10-15 seconds per image
- Parallel (5 workers): ~5 images per 15 seconds
- Parallel (10 workers): ~10 images per 15 seconds (if API allows)

### Open/Closed Variant System

**Openable Categories (Auto-detected):**
- Bathroom: Shower Organizers and Caddies, Storage Bins and Trays, Storage, Waste Baskets and Hampers
- Indoor: Storage (all types), Waste Baskets and Hampers
- Outdoor: Storage Chests

**Mechanism:**
1. Each category has `"openable": true/false` flag in JSON config
2. Generator detects flag and doubles all variants for openable products
3. Generates complete closed set, then complete open set
4. State modifiers appended to prompts for openable products

**State Modifiers (Global):**
```json
"state_open": "Show product OPEN with interior visible and accessible."
"state_closed": "Show product CLOSED with only exterior visible."
```

These global instructions append to any openable product's prompt regardless of shot type. Category prompts describe settings only; state modifiers handle all open/closed logic.

### Shot Type System

#### 1. Room Shots (3 variants, or 6 if openable)
**Purpose:** Lifestyle inspiration and aspiration marketing
**Framing:** Pulled-back perspective showing significant room context
**Usage:** Homepage hero images, lifestyle galleries, social media

#### 2. Tight Shots (3 variants, or 6 if openable)
**Purpose:** Product detail pages and catalog listings
**Framing:** Edge-to-edge, complete product visible
**Usage:** Product detail pages, catalog grids, comparison views

#### 3. Cropped Shots (2 variants, or 4 if openable)
**Purpose:** Premium material quality and craftsmanship showcase
**Framing:** Close-up detail, may crop product edges
**Usage:** Premium product descriptions, quality sections

#### 4. White Refresh (1 variant, or 2 if openable)
**Purpose:** Enhanced catalog shot with better lighting than original
**Framing:** Exact same product and angle as input, pure white background

#### 5. White In-Use (1 variant, or 2 if openable)
**Purpose:** Demonstrates product function on clean background
**Framing:** Same product angle, items placed in/on product

### Naming Convention

**Format:** `SKU - # Type [state] vX.jpg`

**Standard product (SKU 624, non-openable) - 11 files:**
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

**Openable product (SKU 307, hamper) - 21 files:**
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

### Prompt System Architecture

**Four-component structure:**
1. **Product name** - Extracted from input filename
2. **Base prompts** - One per shot type, defines shot characteristics
3. **Category prompts** - Specific to product category, defines setting details
4. **State modifiers** - Only for openable products (open/closed)

**Combination logic:**
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

**Example - Hamper, Room Shot, Open State:**
```
Product: Laundry Hamper. Professional lifestyle photograph. PRODUCT MUST BE 
IDENTICAL to input image - exact same shape, size, construction. Show in 
natural room setting with pulled-back perspective. Few appropriate items nearby. 
Bright studio lighting, clean throughout. Setting: Bathroom, bedroom, or 
laundry room. Positioned against wall. Modern setting, bright lighting. 
STATE: Show product OPEN with interior visible and accessible.
```

### Prompt Design Principles

**Product Identity (Highest Priority):**
Every base prompt includes: "PRODUCT MUST BE IDENTICAL to input image - exact same shape, size, construction"
- Prevents AI from modifying products (moving shelves, changing screws, altering construction)

**Lighting Enforcement:**
All base prompts specify: "Bright studio lighting, clean throughout"
- Eliminates moody/dark shots

**Shot Type Clarity:**
- **Tight:** "Frame product edge-to-edge showing complete item" - entire product visible, minimal margins
- **Cropped:** "Zoom to show texture, materials, craftsmanship details" - AI naturally finds interesting details

**White Shot Isolation:**
White and white-in-use shots use ONLY base prompts + state (if applicable). Category prompts skipped to prevent lifestyle bleed into white backgrounds.

**Generic Language Philosophy:**
- "Few items nearby" instead of "exactly 2-3 items"
- "Close focus on one with others visible" instead of rigid counts
- "Zoom to show details" instead of quantitative crop rules
- Trusts AI to interpret good photography naturally

### Configuration

**category_prompts.json structure:**
```json
{
  "room_variants_per_image": 3,
  "tight_variants_per_image": 3,
  "cropped_variants_per_image": 2,
  "white_variants_per_image": 1,
  "white_in_use_variants_per_image": 1,
  "test_mode_variants_per_image": 1,
  
  "aspect_ratio": "1:1",
  "image_size": "4K",
  
  "max_parallel_requests": 5,
  "api_retry_max_attempts": 3,
  "api_retry_base_delay_seconds": 10,
  "jpeg_quality": 95,
  
  "state_open": "Show product OPEN with interior visible and accessible.",
  "state_closed": "Show product CLOSED with only exterior visible.",
  
  "base_prompt_room": "...",
  "base_prompt_tight": "...",
  "base_prompt_cropped": "...",
  "base_prompt_white": "...",
  "base_prompt_white-in-use": "...",
  
  "categories": {
    "Top Category": {
      "Mid Category": {
        "Granular Category": {
          "prompt": "Category-specific scene description",
          "openable": true
        }
      }
    }
  }
}
```

### Cost & Runtime

**Gemini 3 Pro Image pricing:** ~$0.05 per image at 4K resolution

**Test mode (1 variant per type):**
- ~225 images × $0.05 = ~$11-12
- Runtime with 5 parallel workers: ~8-12 minutes

**Production (350 products, ~50% openable):**
- 175 openable × 20 = 3,500 images
- 175 standard × 10 = 1,750 images
- Total: 5,250 images × $0.05 = ~$260-280
- Runtime with 5 parallel workers: ~3-4 hours

---

## Category Structure

### Openable Categories (8 total)

**Bathroom (4):**
- Shower Organizers and Caddies
- Storage Bins and Trays
- Storage
- Waste Baskets and Hampers

**Indoor (2):**
- Storage
- Waste Baskets and Hampers

**Outdoor (1):**
- Storage Chests

### Non-Openable Categories (22 total)

**Bathroom (4):**
Shower Benches, Floating Wall Shelves, Floor Mats, Towel Racks, Side Tables

**Indoor (9):**
Entryway Benches, Key Holders, Coffee Tables, Shelving, Tissue Boxes and Hangers, Bar and Counter Stools, Countertop Accessories, Dining, Floor Mats

**Outdoor (9):**
Benches, Daybeds, Dining Tables and Chairs, Games, Garden, Lighting, Lounge Chairs/Stools/Ottomans, Parasols, Sofas and Loveseats

### Category-Specific Prompt Details

Prompts address specific visual requirements per category:
- **Floor mats:** "few subtle footprints acceptable" - natural bathroom appearance
- **Hampers/storage:** "positioned against wall" - placement consistency
- **Key hooks:** "at least one hook empty" - natural, not over-staged
- **Towel racks:** "same color tone throughout" - visual coherence
- **Parasols:** "parasol open" - functional display state
- **Games:** "single game setup" - prevents duplication
- **Bar stools:** "close focus on one with others visible" - realistic framing

---

## Execution Pipeline

```bash
# Phase 1: Scrape product catalog
python scraper.py
# Output: aquateak_products/ (~350 products)
# Runtime: ~30-60 minutes

# Phase 2: Test generation (TEST_MODE = True)
python generate_images.py
# Output: 225 test images
# Runtime: ~8-12 minutes (parallel)
# Cost: ~$11-12

# Phase 3: Production generation (TEST_MODE = False)
python generate_images.py
# Output: ~5,250 images
# Runtime: ~3-4 hours (parallel)
# Cost: ~$260-280
```

---

## Output Scale

### Input
- 30 product categories (8 openable, 22 standard)
- ~350 unique products
- 1 image per product from scraper
- 1280x1280 resolution source images

### Output (Production Mode)
- 11 files per standard product (1 original + 10 variants)
- 21 files per openable product (1 original + 20 variants)
- ~5,600 total files for 350 products (50% openable estimate)
- ~11-12 GB total disk space
- Two folder structures: hierarchical + flat

### Processing
- API calls: 5,250 for 350 products
- Parallel workers: 5 concurrent (configurable up to 15-20)
- Retry rate: ~1-2% typical
- Output resolution: 4096px native

---

## Design Decisions

### Why Parallel Processing?

**Problem:** Sequential API calls at 10-15 seconds each meant 15-22 hours for full production run.

**Solution:** ThreadPoolExecutor enables concurrent API calls. 5 workers reduces runtime to ~3-4 hours.

**Trade-offs considered:**
- Higher parallelism risks rate limiting → exponential backoff handles this
- Thread safety concerns → independent tasks with locked logging
- Error isolation → per-variant retries prevent cascade failures

### Why Open/Closed Variants?

**Problem:** Storage products, cabinets, and hampers are used in both states. Single state provided incomplete product documentation.

**Solution:** Auto-detect openable products via category flag, generate both states for all shot types.

**Benefits:**
- Shows product versatility (closed for aesthetics, open for function)
- Complete visual documentation
- Enables A/B testing of conversion rates by state
- Future-proofs catalog

**Trade-off:** 2x variants for openable products = ~50% cost increase for affected categories. Accepted for comprehensive coverage.

### Why Global State Modifiers?

**Problem:** Embedding open/closed logic in 30 category prompts creates redundancy and maintenance burden.

**Solution:** Single global instruction appended to openable product prompts:
- `"Show product OPEN with interior visible and accessible."`
- `"Show product CLOSED with only exterior visible."`

**Benefits:**
- Separation of concerns: category = setting, state modifier = product state
- Single point of maintenance
- Clean prompt composition
- AI receives clear, unconditional instruction

### Why Generic Prompt Language?

**Problem:** Over-specific prompts cause generation failures:
- "Show exactly 2-3 items" → rigid counting creates unnatural scenes
- "Cropped at waist" → fails if product has no waist equivalent
- "Less than half visible" → quantitative rules are brittle

**Solution:** Generic, interpretable language:
- "Few items nearby" → AI places natural amount
- "Close focus on one" → AI frames naturally
- "Zoom to show details" → AI finds interesting details

**Result:** Higher success rate, more natural-looking outputs, fewer regeneration cycles.

### Why White Shot Isolation?

**Problem:** Category prompts describing "bathroom with wet tile" or "garden setting" bleed into white background shots.

**Solution:** White and white-in-use shots skip category prompts entirely. Only base prompt + state modifier (if applicable) used.

**Result:** Pure white backgrounds maintained regardless of product category.

---

## Dependencies

### Python Packages
```
requests         # HTTP requests for scraping and API calls
beautifulsoup4   # HTML parsing for category extraction
pillow           # Image manipulation and format conversion
tqdm             # Progress bars with nested display
```

### System Requirements
- Python 3.7+
- 15+ GB free disk space
- 2+ GB RAM
- Stable internet connection

### API
- Gemini API key from Google AI Studio
- Model: `gemini-3-pro-image-preview`
- Resolution: 4096px (4K native)

---

## Model Information

### Current Model
- **Name:** `gemini-3-pro-image-preview`
- **Provider:** Google AI Studio
- **Resolution:** 4096px native
- **Generation time:** ~10-15 seconds per image

### Known Behaviors
- Free tier adds SynthID watermarks
- Rate limiting exists (handled by exponential backoff)
- Preview model behavior may evolve
- Occasional 503 errors under high load (retry logic handles this)