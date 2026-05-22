# Product Image AI Generation Pipeline

Automated workflow for transforming white-background product photography into professionally styled lifestyle imagery using Google's Gemini image generation API (Nano Banana Pro).

## Architecture Overview

```
project/
├── inputs/
│   └── run2/                  # Source images (hierarchical by category)
├── outputs/
│   ├── generated_images/      # Final output (flat: one folder per SKU)
│   └── batch_jobs/            # Batch JSONL files + state.json
├── prompts/
│   ├── shot_prompts.json      # Base prompts + state modifiers
│   └── category_prompts.json  # Category-specific scene descriptions
├── logs/
│   ├── errors.log             # Verbose error log (stack traces, raw responses)
│   ├── failed_chunkN_*.txt    # Per-chunk failure lists
│   └── scraper_log.txt        # Scraper error log
├── generate_images.py         # Main generation script
├── scraper.py                 # Product image scraper
└── apikey.txt                 # Gemini API key (raw key, no quotes)
```

## Design Decisions

### Batch API Only
The pipeline uses Google's Batch API exclusively (real-time mode removed).

**Rationale**: Batch is 50% cheaper than real-time with identical output quality. Real-time mode also hits Tier 1's 250 RPD cap on preview models, making it unusable for jobs >250 images. Batch has no daily cap.

### Flat Output Structure
Output is one folder per SKU: `outputs/generated_images/[SKU]/`, containing the original copy + all generated variants.

**Rationale**: SKU is the meaningful unit. Category hierarchy is preserved in input folders for prompt-routing only. Flat output is faster to browse, easier to bulk-upload, and matches how downstream systems consume product imagery.

### Filename Convention
Inputs: `[SKU] Product Name.jpg` (e.g., `[293] Spa-Mist Teak Bath & Shower Mat.jpg`)
Outputs: `[SKU] - N Shot Type vK.jpg` (e.g., `[293] - 1 White refresh v1.jpg`)

**Rationale**: Bracketed SKU is unambiguous to regex parse and visually distinct from product name. Numeric shot prefix (0=original, 1=white, 2=in-use, 3=room, 4=tight, 5=cropped) keeps files sorted by shot type.

### Crash-Safe State Tracking
Every batch submission writes `outputs/batch_jobs/state.json` (atomic tmp+rename). Every status change updates the same file.

**Rationale**: Internet drops, power loss, ctrl+c, or crash mid-run lose no work. Re-running the script detects the state file and resumes. Submitted batches are tracked by name; completed images detected by filesystem.

### Idempotent Execution
Script detects existing outputs (file exists + >1KB) and skips. Submitted chunks tracked in state file.

**Rationale**: Safe to re-run any time. No duplicate API charges. Can incrementally add new products without re-generating existing ones.

### Chunked Batch Processing
Jobs split into 500-image chunks, each submitted as a separate batch job.

**Rationale**: Stays well under Tier 1's 2M enqueued-token cap for Nano Banana Pro. Limits blast radius of any single failure. Enables parallel processing on Google's side (up to 100 concurrent batches). Zero cost penalty — same total tokens either way.

### Free API Key Verification
On startup, calls `client.models.list()` to verify the key works before any billable operation.

**Rationale**: `models.list` consumes zero tokens. Catches missing/invalid/wrong-tier keys before users incur charges.

### Double Confirmation
Before submission, requires `y` + then exact uppercase `YES`.

**Rationale**: Jobs cost real money (hundreds of dollars typical). Two-step confirm prevents accidental submission.

## Shot Types

| # | Type | Aspect Ratio | Description |
|---|------|--------------|-------------|
| 0 | Original | As-is | Source image (copied) |
| 1 | White refresh | 1:1 | Clean white background |
| 1A | White fitted | Dynamic* | White background, native AR |
| 2 | White in use | 1:1 | Product with human interaction |
| 2A | White in use fitted | Dynamic* | In-use, native AR |
| 3 | Full room | 1:1 | Complete room scene |
| 4 | Tight | 1:1 | Close-up detail shot |
| 5 | Cropped | 1:1 | Artistic crop/composition |

*Dynamic aspect ratio matches source image from 10 supported ratios.

## Usage

### Basic Generation
```bash
python generate_images.py
# Flow:
#   1. Verifies API key (free)
#   2. Scans inputs, lists work to do
#   3. Shows full cost breakdown
#   4. Double-confirm: y, then YES (uppercase)
#   5. Submits chunks, polls every 60s, downloads as ready
```

### Resume After Crash / Interruption
```bash
python generate_images.py
# Detects state.json automatically.
# Prompts: [R]esume / [N]ew run / [Q]uit
# Pick R to continue polling submitted batches.
```

### Scrape Source Images
```bash
python scraper.py
```

## Configuration

All settings at top of `generate_images.py`:

```python
# Folders
INPUT_FOLDER = "inputs/run2"
OUTPUT_FOLDER = "outputs/generated_images"

# Model
GEMINI_MODEL = "gemini-3-pro-image-preview"   # Nano Banana Pro
DEFAULT_IMAGE_SIZE = "4K"                     # "512" | "1K" | "2K" | "4K"
DEFAULT_ASPECT_RATIO = "1:1"

# Batch
CHUNK_SIZE = 500              # imgs per batch job (under 2M token cap)
INTER_SUBMIT_DELAY = 2.0      # seconds between chunk submissions
UPLOAD_MAX_RETRIES = 5        # retries for upload/submit/download
POLL_INTERVAL = 60            # seconds between status checks

# Variants per shot type
VARIANTS_PRODUCTION = {
    'white': 1, 'white_fitted': 1,
    'white_in_use': 2, 'white_in_use_fitted': 2,
    'room': 2, 'tight': 3, 'cropped': 3,
}
```

## API Rate Limits (Tier 1)

| Limit | Value | Notes |
|---|---|---|
| Real-time IPM (images/min) | ~10-25 | Not used (batch only) |
| Real-time RPD (requests/day) | ~250 | Hard cap on preview models |
| Batch enqueued tokens (Pro Image) | 2,000,000 | Per model, across all active batches |
| Batch concurrent jobs | 100 | Plenty of headroom |
| Batch file size | 2 GB | One chunk ~80MB |

Tier upgrades unlock automatically as billed spend accrues. Tier 2 at $100 spend, Tier 3 at $1000.

## Pricing (Nano Banana Pro, Batch API)

| Component | Tokens | Rate | Per image |
|---|---|---|---|
| Text prompt | ~400 | $1.00/M | ~$0.0004 |
| Input image | 560 | $0.55/M | ~$0.0003 |
| Output image (4K) | 2,000 | $60/M | $0.12 |
| **Total per image (4K batch)** | | | **~$0.121** |

| Resolution | Real-time | Batch (−50%) |
|---|---|---|
| 1K / 2K | $0.134 | $0.067 |
| **4K (default)** | **$0.24** | **$0.12** |

### Cost Estimates (4K batch)

| Images | Cost |
|---|---|
| 100 | ~$12 |
| 1,000 | ~$121 |
| 10,000 | ~$1,210 |

Monitor live spend: https://aistudio.google.com/usage

## Error Handling

- **Network/API errors**: Upload/submit/download retry 5× with linear backoff (30s → 150s)
- **Rate limits (429/RESOURCE_EXHAUSTED)**: Caught and retried with backoff
- **Batch-level failures**: Logged, marked in state, other chunks unaffected
- **Per-image failures**: Counted, listed in `logs/failed_chunkN_*.txt` with full context
- **Filename parse failures**: Skipped, listed in `logs/errors.log`, run continues
- **Crash / interrupt**: State file preserved, re-run to resume from exact point
- **Verbose error log**: `logs/errors.log` captures stack traces + API response context for every failure
- **Skip detection**: Existing files detected by path + size threshold (>1KB)

## Dependencies

```
google-genai
pillow
tqdm
requests
beautifulsoup4  # scraper only
```

## Scraper Features

- Extracts category hierarchy from site navigation
- Global SKU deduplication across categories
- White background validation (85% perimeter threshold)
- Detailed error logging by category
- Pagination support for large categories