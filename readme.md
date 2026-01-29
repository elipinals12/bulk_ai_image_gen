# Product Image AI Generation Pipeline

Complete automated workflow for transforming white-background product photography into professionally styled lifestyle imagery using AI image generation.

---

## Recent Updates (January 2026)

### Config File Restructure (NEW)
- **Settings moved to Python** - All configuration (variants, API settings, folders) now in `generate_images.py`
- **Prompts split into two files:**
  - `shot_prompts.json` - Base prompts for each shot type + open/closed state modifiers
  - `category_prompts.json` - Category-specific scene descriptions

### Fitted Aspect Ratio Variants (NEW)
- **Smart aspect ratio detection** - Analyzes input image dimensions to pick best matching Gemini ratio
- **New "fitted" white variants** - White shots that match product shape instead of forcing 1:1 square
- **10 supported ratios:** 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9
- Example: Tall shelf (800x1200) → detects 0.667 ratio → uses "2:3" for fitted shots

### Parallel Processing System
- **Concurrent API calls** using ThreadPoolExecutor for ~5x speed improvement
- **Configurable parallelism** via `MAX_PARALLEL_REQUESTS` in Python config
- **Thread-safe logging** prevents race conditions during parallel execution
- **Automatic rate limit handling** with exponential backoff (10s → 20s → 40s)

### Open/Closed Variant System
- **Automatic detection** of openable products (cabinets, hampers, storage)
- **Doubles all variants** for openable products - generates both closed AND open states
- **Smart state modifiers** in `shot_prompts.json` control open/closed instructions

---

## File Structure

```
project/
├── generate_images.py      # Main script + ALL settings
├── shot_prompts.json       # Base prompts + state modifiers
├── category_prompts.json   # Category scene descriptions
├── apikey.txt              # Gemini API key
└── aquateak_products/      # Input images (organized by category)
```

### Configuration in generate_images.py

```python
# --- Mode Settings ---
TEST_MODE = True

# --- API Settings ---
GEMINI_MODEL = "gemini-3-pro-image-preview"
MAX_PARALLEL_REQUESTS = 10
API_RETRY_MAX_ATTEMPTS = 3
API_RETRY_BASE_DELAY_SECONDS = 10

# --- Output Settings ---
DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_IMAGE_SIZE = "4K"      # Options: "1K", "2K", "4K" (must be uppercase!)
JPEG_QUALITY = 95

# --- Variant Counts (Production Mode) ---
VARIANTS_PRODUCTION = {
    'white': 1,
    'white_fitted': 1,
    'white_in_use': 2,
    'white_in_use_fitted': 2,
    'room': 2,
    'tight': 5,
    'cropped': 3,
}
```

---

## Shot Types

| # | Name | Description | Aspect Ratio |
|---|------|-------------|--------------|
| 0 | Original | Source image copy | As-is |
| 1 | White refresh | Enhanced white background | 1:1 square |
| 1A | White fitted | White background, product-fit ratio | Dynamic |
| 2 | White in use | White background with props | 1:1 square |
| 2A | White in use fitted | White with props, product-fit ratio | Dynamic |
| 3 | Full room | Lifestyle room setting | 1:1 square |
| 4 | Tight | Edge-to-edge product framing | 1:1 square |
| 5 | Cropped | Close-up detail shot | 1:1 square |

---

## Naming Convention

**Standard product (SKU 624, non-openable):**
```
624 - 0 Original.jpg
624 - 1 White refresh v1.jpg
624 - 1A White fitted v1.jpg
624 - 2 White in use v1.jpg
624 - 2 White in use v2.jpg
624 - 2A White in use fitted v1.jpg
624 - 2A White in use fitted v2.jpg
624 - 3 Full room v1.jpg
624 - 3 Full room v2.jpg
624 - 4 Tight v1.jpg
...
624 - 5 Cropped v3.jpg
```

**Openable product (SKU 307, hamper):**
```
307 - 0 Original.jpg
307 - 1 White refresh closed v1.jpg
307 - 1 White refresh open v1.jpg
307 - 1A White fitted closed v1.jpg
307 - 1A White fitted open v1.jpg
...
```

---

## Fitted Aspect Ratio System

### How It Works

1. **Read input image dimensions** (e.g., 800 x 1200 pixels)
2. **Calculate ratio** (800 / 1200 = 0.667)
3. **Find closest Gemini-supported ratio** (0.667 ≈ 2:3)
4. **Use for fitted variants** (1A, 2A shots use "2:3")

### Supported Ratios

| Ratio | Decimal | Best For |
|-------|---------|----------|
| 1:1 | 1.0 | Square products |
| 2:3 | 0.667 | Tall portrait |
| 3:2 | 1.5 | Wide landscape |
| 3:4 | 0.75 | Portrait |
| 4:3 | 1.333 | Landscape |
| 4:5 | 0.8 | Instagram portrait |
| 5:4 | 1.25 | Landscape |
| 9:16 | 0.5625 | Very tall (Stories) |
| 16:9 | 1.778 | Widescreen |
| 21:9 | 2.333 | Ultra-wide |

---

## Prompt System

### Three-Layer Structure

1. **Product name** - Extracted from input filename
2. **Base prompt** - From `shot_prompts.json`, defines shot characteristics
3. **Category prompt** - From `category_prompts.json`, defines scene/setting (room/tight/cropped only)
4. **State modifier** - From `shot_prompts.json`, open/closed instructions (openable products only)

### shot_prompts.json

```json
{
  "base_prompts": {
    "room": "Professional lifestyle photograph. PRODUCT MUST BE IDENTICAL...",
    "tight": "Professional lifestyle photograph with tight framing...",
    "cropped": "Close-up detail shot...",
    "white": "Pure white seamless background...",
    "white-in-use": "White background with props...",
    "white-fitted": "White background, tight framing...",
    "white-in-use-fitted": "White with props, tight framing..."
  },
  "state_modifiers": {
    "open": "Show product OPEN with interior visible...",
    "closed": "Show product CLOSED with only exterior visible."
  }
}
```

### category_prompts.json

```json
{
  "categories": {
    "Bathroom": {
      "Bath Accessories": {
        "Floor Mats": {
          "prompt": "Bathroom floor near shower or tub. Wet surface around mat...",
          "openable": false
        }
      }
    }
  }
}
```

---

## API Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `imageSize` | "4K" | Must be uppercase. Options: "1K", "2K", "4K" |
| `aspectRatio` | varies | 10 supported values, see table above |
| `jpeg_quality` | 95 | PIL save parameter (0-100), not Gemini |

---

## Execution

```bash
# Test mode (1 variant per type)
# Set TEST_MODE = True in generate_images.py
python generate_images.py

# Production mode (full variants)
# Set TEST_MODE = False in generate_images.py
python generate_images.py
```

---

## Output

- **Hierarchical:** `generated_images/` (organized by category)
- **Flat:** `all_generated/` (all images in one folder)
- **Logs:** `generation_log.txt` (errors and failures)

---

## Cost & Runtime

**Gemini 3 Pro Image pricing:** ~$0.05-0.24 per image depending on resolution

**Test mode:** ~8-12 minutes, ~$15

**Production (350 products, ~50% openable):** ~3-4 hours, ~$300-400

---

## Dependencies

```
requests
beautifulsoup4
pillow
tqdm
```