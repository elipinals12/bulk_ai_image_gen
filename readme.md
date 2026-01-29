# Product Image AI Generation Pipeline

Complete automated workflow for transforming white-background product photography into professionally styled lifestyle imagery using AI image generation.

---

## Recent Updates (January 2026)

### Safe Resume Mode (NEW - Jan 29)
- **No deletion of progress** - Script now preserves `generated_images/` folder between runs
- **Smart skip detection** - Scans existing files and only generates missing ones
- **Run multiple times safely** - Just re-run to complete incomplete batches

### Rate Limit Fix (NEW - Jan 29)
- **Tier 1 limit: 10 images/minute** - Previous 10-worker config exceeded this
- **Now uses 2 workers + 7s delay** - Stays safely at ~8 images/min
- **Better retry logic** - 30s base delay, 5 attempts, handles 429 and 503 errors

### Config File Restructure
- **Settings moved to Python** - All configuration in `generate_images.py`
- **Prompts split into two files:**
  - `shot_prompts.json` - Base prompts + state modifiers
  - `category_prompts.json` - Category scene descriptions

### Fitted Aspect Ratio Variants
- **Smart aspect ratio detection** - Analyzes input image to pick best Gemini ratio
- **10 supported ratios:** 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9

---

## Gemini API Rate Limits

| Tier | IPM (Images/Min) | How to Qualify |
|------|------------------|----------------|
| Free | 2 | Default |
| **Tier 1** | **10** | Enable billing |
| Tier 2 | 50 | $250 spend + 30 days |
| Tier 3 | 100 | $1,000 spend + 30 days |

**Current safe settings (Tier 1):**
```python
MAX_PARALLEL_REQUESTS = 2      # DO NOT increase for Tier 1
MIN_REQUEST_INTERVAL = 7.0     # ~8 images/min (under 10 limit)
```

---

## File Structure

```
project/
├── generate_images.py      # Main script + ALL settings
├── shot_prompts.json       # Base prompts + state modifiers
├── category_prompts.json   # Category scene descriptions
├── apikey.txt              # Gemini API key
├── aquateak_products/      # Input images
├── generated_images/       # Output (PRESERVED between runs!)
└── all_generated/          # Flat copy (recreated each run)
```

---

## Usage

```bash
# First run - generates everything
python generate_images.py

# After failures - just run again!
# Script automatically skips completed files
python generate_images.py

# Keep running until 100% complete
python generate_images.py
```

**Output example:**
```
✓ Already completed: 750 images (skipped)
→ Remaining to generate: 50 images
→ Estimated time: 6 min (0.1 hours)
```

---

## Configuration in generate_images.py

```python
# --- Mode ---
TEST_MODE = False  # True = 1 variant each, False = full production

# --- Rate Limit Safe Settings (Tier 1 = 10 IPM) ---
MAX_PARALLEL_REQUESTS = 2          # Don't increase for Tier 1!
MIN_REQUEST_INTERVAL = 7.0         # Seconds between requests
API_RETRY_MAX_ATTEMPTS = 5         # Retries per image
API_RETRY_BASE_DELAY_SECONDS = 30  # Wait time on rate limit

# --- Variants ---
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

| # | Name | Aspect Ratio |
|---|------|--------------|
| 0 | Original | As-is |
| 1 | White refresh | 1:1 |
| 1A | White fitted | Dynamic |
| 2 | White in use | 1:1 |
| 2A | White in use fitted | Dynamic |
| 3 | Full room | 1:1 |
| 4 | Tight | 1:1 |
| 5 | Cropped | 1:1 |

---

## Cost & Runtime (Tier 1)

| Scenario | Images | Time | Cost |
|----------|--------|------|------|
| Test mode | ~50 | ~6 min | ~$12 |
| Production (350 products) | ~7,800 | ~16 hours | ~$1,900 |

**Pricing:** $0.24 per 4K image (Gemini 3 Pro Image)

---

## Troubleshooting

### "Rate limit exceeded after N attempts"
Your tier's IPM limit was hit. The updated script handles this automatically with longer delays. Just re-run.

### Many failures on first run
Normal if you had too many workers. The safe resume will pick up where it left off.

### Want faster generation?
Upgrade to Tier 2 ($250 Google Cloud spend + 30 days) for 50 IPM, then increase:
```python
MAX_PARALLEL_REQUESTS = 8
MIN_REQUEST_INTERVAL = 1.5  # ~40 images/min
```

---

## Dependencies

```
requests
pillow
tqdm
```