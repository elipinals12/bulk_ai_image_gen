# Product Image AI Generation Pipeline

Automated workflow for transforming white-background product photography into professionally styled lifestyle imagery using Google's Gemini image generation API.

## Architecture Overview

```
project/
├── inputs/
│   └── aquateak_products/     # Source images (hierarchical by category)
├── outputs/
│   ├── generated_images/      # Final output (mirrors input structure)
│   └── batch_jobs/            # Batch API state files
├── prompts/
│   ├── shot_prompts.json      # Base prompts + state modifiers
│   └── category_prompts.json  # Category-specific scene descriptions
├── logs/
│   ├── scraper_log.txt        # Scraper error log
│   └── temp_batch_download.jsonl
├── generate_images.py         # Main generation script
├── scraper.py                 # Product image scraper
└── apikey.txt                 # Gemini API key
```

## Design Decisions

### Dual API Mode Support
The pipeline supports both real-time and batch API modes, selectable at runtime:

| Mode | Cost | Latency | Use Case |
|------|------|---------|----------|
| Real-time | $0.24/image | Immediate | Small batches, testing, urgent needs |
| Batch | $0.12/image | 1-24 hours | Production runs, cost optimization |

**Rationale**: Batch API provides 50% cost savings for large production runs where immediate results aren't required. Real-time mode enables rapid iteration during development.

### Hierarchical Output Structure
Output mirrors input folder hierarchy (`Category/Subcategory/Type/SKU/`) rather than flat organization.

**Rationale**: Preserves semantic relationships, enables selective regeneration of specific categories, and maintains traceability to source products.

### Idempotent Execution
Script detects existing outputs and skips completed work. Safe to run multiple times.

**Rationale**: Enables recovery from failures, incremental generation, and safe resumption after interruptions without data loss or duplicate work.

### Chunked Batch Processing
Large jobs split into 1000-image chunks, each as separate batch job.

**Rationale**: Prevents single points of failure, enables parallel processing on Google's side, and keeps individual file sizes manageable (~200MB per chunk).

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
# Prompts:
#   1. Test mode? (y/n)
#   2. API mode: [1] Real-time or [2] Batch
```

### Resume Interrupted Batch
```bash
python generate_images.py --resume outputs/batch_jobs/all_batches_YYYYMMDD-HHMMSS.json
```

### Scrape Source Images
```bash
python scraper.py
```

## Configuration

All settings in `generate_images.py` header:

```python
# Folders
INPUT_FOLDER = "inputs/aquateak_products"
OUTPUT_FOLDER = "outputs/generated_images"

# Generation
CHUNK_SIZE = 1000          # Images per batch job

# Real-time rate limiting (Tier 1 = 10 IPM)
MAX_PARALLEL_REQUESTS = 2
MIN_REQUEST_INTERVAL = 7.0

# Variants per shot type
VARIANTS_PRODUCTION = {
    'white': 1, 'white_fitted': 1,
    'white_in_use': 2, 'white_in_use_fitted': 2,
    'room': 2, 'tight': 5, 'cropped': 3,
}
```

## API Rate Limits

| Tier | Images/Min | Qualification |
|------|------------|---------------|
| Free | 2 | Default |
| Tier 1 | 10 | Enable billing |
| Tier 2 | 50 | $250 spend + 30 days |
| Tier 3 | 100 | $1,000 spend + 30 days |

Default settings configured for Tier 1. Adjust `MAX_PARALLEL_REQUESTS` and `MIN_REQUEST_INTERVAL` for higher tiers.

## Cost Estimates

| Mode | 100 images | 1,000 images | 10,000 images |
|------|------------|--------------|---------------|
| Real-time | $24 | $240 | $2,400 |
| Batch | $12 | $120 | $1,200 |

## Error Handling

- **Rate limits**: Exponential backoff with configurable retry attempts
- **Batch failures**: Per-chunk isolation prevents total job loss
- **Resume support**: Batch state persisted to JSON for recovery
- **Skip detection**: Existing files detected by size threshold (>1KB)

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