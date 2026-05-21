"""
Extract White Shots from Messy Local Folder Tree
=================================================
For each [SKU] Name folder in the messy input, picks ONE best white shot and
copies it (renamed to [SKU] Name.ext) into the proper category hierarchy.

Best-shot picking (deterministic):
    1. *WS #1_hq*  ->  preferred
    2. *WS #1*     ->  fallback
    3. lowest numeric #N        ->  fallback
    4. first file alphabetically -> last resort

Categorization (in order):
    1. SKU exists in reference tree (your "categorized/" folder)  -> use that category
    2. Keyword match on product name (shower, knife, hamper, etc) -> auto-categorize
    3. Neither           -> dump in _unmatched/ for manual handling

Paths are hardcoded at the top of this file - edit the CONFIG block to change.

Run:
    python extract_whiteshots.py
"""

import os
import re
import sys
import json
import shutil
from datetime import datetime
from collections import defaultdict

from tqdm import tqdm

# ============================================================================
# CONFIG (hardcoded - edit here)
# ============================================================================

INPUT_TREE = "/home/eli/Documents/bulkimgen/inputs/run2"
REFERENCE_TREE = "/home/eli/Documents/bulkimgen/inputs/categorized"
OUTPUT_DIR = "/home/eli/Documents/bulkimgen/inputs/run2_categorized"

# Behavior flags
DELETE_AFTER_SORT = True   # delete source [SKU] folder once successfully sorted
DRY_RUN = False            # if True: log only, no copies, no deletes

# ============================================================================
# MANUAL SKU OVERRIDES
# ============================================================================
# For SKUs that aren't in the reference tree (new products, color variant bases).
# Two modes:
#   1. NAME ONLY -> {"name": "..."}
#      Preserves the title in the output filename but routes to _unmatched/
#      Use this when you have the product name but aren't sure about category.
#   2. FULL OVERRIDE -> {"name": "...", "top": "...", "mid": "...", "gran": "..."}
#      Auto-categorizes into the given top/mid/gran folder.
#      Use this only when you're confident about category placement.
# ============================================================================

SKU_OVERRIDES = {
    "190": {
        "name": "18 Asia® Decorative Wood Bench",
        # name-only -> color variants will get proper name but route to _unmatched/
    },
    # Add more entries here as needed. Examples:
    # "451": {"name": "Mesa Large Teak Lantern"},  # name-only
    # "999": {"name": "Foo", "top": "Indoor", "mid": "Living Room", "gran": "Storage"},
}

LOG_FOLDER = "logs"
LOG_FILE = os.path.join(LOG_FOLDER, "extract_whiteshots_log.txt")
SKU_MAP_CACHE = os.path.join(LOG_FOLDER, "sku_category_map.json")

# Folders to search for whiteshots
WHITE_FOLDER_NAMES = {
    "white", "white background", "white shots", "whiteshots",
    "whites", "white shot", "ws",
}

# Folders explicitly NOT recursed into
SKIP_FOLDER_NAMES = {
    "360 view", "360", "lifestyle", "dimensions", "dimension",
    "drawings", "drawing", "raw", "picture", "gif",
}

IMG_EXTS = {".jpg", ".jpeg", ".png"}

# ============================================================================
# Logging
# ============================================================================

class Logger:
    def __init__(self):
        self.events = defaultdict(list)            # bucket -> list of events (failures/warnings)
        self.successes = []                        # list of compact one-line dicts
        self.failures = []                         # list of multi-line failure dicts

    def add(self, bucket, sku, message, **extra):
        self.events[bucket].append({"sku": sku, "message": message, "extra": extra})

    def log_success(self, sku, dest_category, source_file, dest_path, via):
        """Compact success: 1 line in the log."""
        self.successes.append({
            "sku": sku, "category": dest_category, "source_file": source_file,
            "dest": dest_path, "via": via,
        })

    def log_failure(self, sku, status, reason, source_folder, **extra):
        """Verbose failure: full block in the log with reasoning."""
        self.failures.append({
            "sku": sku, "status": status, "reason": reason,
            "source_folder": source_folder, "extra": extra,
        })

    def write(self, summary):
        os.makedirs(LOG_FOLDER, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("=" * 96 + "\n")
            f.write("EXTRACT WHITESHOTS - LOG\n")
            f.write(f"Timestamp:  {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            f.write("=" * 96 + "\n\n")

            f.write("SUMMARY\n")
            f.write("-" * 96 + "\n")
            for k, v in summary.items():
                f.write(f"  {k:<44} {v}\n")
            f.write("\n")

            # ---- FAILURES FIRST (most important to review) ----
            if self.failures:
                f.write("\n" + "=" * 96 + "\n")
                f.write(f"NEEDS ATTENTION  ({len(self.failures)})  -- source folders left in place\n")
                f.write("=" * 96 + "\n\n")
                for fl in sorted(self.failures, key=lambda x: _sku_sort_key(x["sku"])):
                    f.write(f"  [{fl['sku']}]  {fl['status']}\n")
                    f.write(f"      reason: {fl['reason']}\n")
                    f.write(f"      source: {fl['source_folder']}\n")
                    for k, v in (fl.get("extra") or {}).items():
                        f.write(f"      {k}: {v}\n")
                    f.write("\n")

            # ---- SUCCESSES: compact, one line each ----
            if self.successes:
                f.write("\n" + "=" * 96 + "\n")
                f.write(f"SUCCESSFULLY SORTED  ({len(self.successes)})  -- source folders deleted\n")
                f.write("=" * 96 + "\n\n")
                for s in sorted(self.successes, key=lambda x: _sku_sort_key(x["sku"])):
                    f.write(f"  [{s['sku']}] {s['via']:<14} -> {s['category']}   "
                            f"(picked: {s['source_file']})\n")
                f.write("\n")

            # ---- Additional event buckets (debug detail) ----
            if self.events:
                f.write("\n" + "=" * 96 + "\n")
                f.write("ADDITIONAL EVENTS (debug detail)\n")
                f.write("=" * 96 + "\n\n")
                for bucket in sorted(self.events.keys()):
                    evs = self.events[bucket]
                    f.write(f"\n{bucket}  ({len(evs)})\n")
                    f.write("-" * 96 + "\n")
                    for e in evs:
                        f.write(f"  SKU: {e['sku']} - {e['message']}\n")
                        for k, v in (e.get("extra") or {}).items():
                            f.write(f"      {k}: {v}\n")
                    f.write("\n")

log = Logger()

def info(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")

def _sku_sort_key(sku):
    m = re.match(r"(\d+)(.*)", sku)
    return (int(m.group(1)), m.group(2)) if m else (10**9, sku)

# ============================================================================
# Sanitization (matches scraper.py rules)
# ============================================================================

def sanitize_folder_name(name):
    name = name.replace("&", "and").replace('"', " inch")
    for c in ["/", "\\", ":", "*", "?", "<", ">", "|"]:
        name = name.replace(c, "")
    return re.sub(r"\s+", " ", name.replace("™", "").replace("®", "")).strip()

def sanitize_filename(name):
    name = name.replace('"', " inch")
    for c in ["/", "\\", ":", "*", "?", "<", ">", "|"]:
        name = name.replace(c, "-" if c in ["/", "\\"] else "")
    return re.sub(r"\s+", " ", name.replace("™", "").replace("®", "")).strip()

# ============================================================================
# Parsing
# ============================================================================

SKU_FOLDER_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
LEGACY_FILENAME_RE = re.compile(r"^([A-Za-z0-9\-_]+)\s*-\s*(.+)$")

# Color words that appear as SKU suffixes (e.g. [190-BLACK]).
# Maps full color word -> abbreviated form used in actual filenames.
COLOR_FULL_TO_ABBREV = {
    "BLACK": "B",
    "BLUE": "BL",
    "GREY": "G",
    "GRAY": "G",
    "RED": "R",
    "WHITE": "W",
    "GREEN": "GR",
    "BROWN": "BR",
}

def detect_color_variant(sku):
    """If SKU like '190-BLACK', returns (base_sku='190', color_abbrev='B', color_word='BLACK').
       Otherwise (None, None, None)."""
    if "-" not in sku:
        return None, None, None
    base, _, suffix = sku.rpartition("-")
    suffix_u = suffix.upper()
    if suffix_u in COLOR_FULL_TO_ABBREV:
        return base, COLOR_FULL_TO_ABBREV[suffix_u], suffix_u
    return None, None, None

def parse_sku_folder(folder_basename):
    """'[100] 18 Asia...' -> ('100', '18 Asia...'). '[190-BLACK]' -> ('190-BLACK', '')."""
    m = SKU_FOLDER_RE.match(folder_basename.strip())
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()

def parse_reference_filename(fname):
    """'100 - Slatted Bench.jpg' -> ('100', 'Slatted Bench')
       Also handles new '[100] Slatted Bench.jpg' format."""
    stem, _ = os.path.splitext(fname)
    m_new = SKU_FOLDER_RE.match(stem.strip())
    if m_new:
        return m_new.group(1).strip(), (m_new.group(2).strip() or m_new.group(1).strip())
    m_old = LEGACY_FILENAME_RE.match(stem.strip())
    if m_old:
        return m_old.group(1).strip(), m_old.group(2).strip()
    return None, None

# ============================================================================
# Phase 1: build SKU -> category from reference tree
# ============================================================================

def build_sku_map_from_reference(ref_root):
    """Walk ref_root/{top}/{mid}/{gran}/{file} and build {sku: {top, mid, gran, name}}."""
    if not os.path.isdir(ref_root):
        info(f"  X Reference tree not found: {ref_root}")
        return None

    info(f"Walking reference tree: {ref_root}")
    sku_map = {}
    files_seen = skipped = 0
    for dirpath, _, filenames in os.walk(ref_root):
        rel = os.path.relpath(dirpath, ref_root)
        if rel == ".":
            continue
        parts = rel.split(os.sep)
        if len(parts) != 3:
            continue
        top, mid, gran = parts
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() not in IMG_EXTS:
                continue
            files_seen += 1
            sku, name = parse_reference_filename(fname)
            if not sku:
                log.add("Reference: Unparseable filename", "?", f"file={fname}",
                        path=os.path.join(dirpath, fname))
                skipped += 1
                continue
            if sku in sku_map:
                ex = sku_map[sku]
                if (ex["top"], ex["mid"], ex["gran"]) != (top, mid, gran):
                    log.add("Reference: SKU in multiple categories", sku,
                            f"keeping {ex['top']}/{ex['mid']}/{ex['gran']}; "
                            f"ignoring {top}/{mid}/{gran}")
                continue
            sku_map[sku] = {"top": top, "mid": mid, "gran": gran, "name": name}

    info(f"  -> {files_seen} files scanned, {len(sku_map)} unique SKUs ({skipped} unparseable)")
    os.makedirs(LOG_FOLDER, exist_ok=True)
    with open(SKU_MAP_CACHE, "w") as f:
        json.dump(sku_map, f, indent=2)
    info(f"  -> Cached to {SKU_MAP_CACHE}")
    return sku_map

# ============================================================================
# Phase 2: walk + find best white shot
# ============================================================================

def find_white_folders(product_root):
    """Recursive scan. Skip SKIP_FOLDER_NAMES subtrees. Returns dirs with whitelisted name."""
    matches = []
    for dirpath, dirnames, _ in os.walk(product_root):
        dirnames[:] = [d for d in dirnames if d.strip().lower() not in SKIP_FOLDER_NAMES]
        if os.path.basename(dirpath).strip().lower() in WHITE_FOLDER_NAMES:
            matches.append(dirpath)
    return matches

def list_image_files(folder):
    """Top-level images in folder."""
    out = []
    try:
        for entry in os.listdir(folder):
            full = os.path.join(folder, entry)
            if os.path.isfile(full) and os.path.splitext(entry)[1].lower() in IMG_EXTS:
                out.append((entry, full))
    except OSError as e:
        log.add("Cannot list folder", "?", f"{folder}: {e}")
    return out

# Regex captures shot number from:
#   "WS #1", "WS#1", "#1", "(1)", "_1", "(10)", "WS #10_hq"
SHOT_NUM_RE = re.compile(r"(?:ws\s*#|#|\()\s*(\d+)", re.IGNORECASE)

def pick_best_whiteshot(files):
    """Score each file: (shot_number, hq_penalty). Lower = better. Return single (fname, path)."""
    if not files:
        return None
    if len(files) == 1:
        return files[0]

    def score(item):
        fname = item[0].lower()
        m = SHOT_NUM_RE.search(fname)
        shot_num = int(m.group(1)) if m else 999
        is_hq = "_hq" in fname
        # lower score wins -> low shot_num + hq preferred
        return (shot_num, 0 if is_hq else 1, fname)

    return sorted(files, key=score)[0]

# ============================================================================
# Phase 3: keyword categorization (for SKUs not in reference)
# ============================================================================
#
# Returns (top, mid, gran, confidence) or None.
# Order MATTERS - more specific patterns first. Confidence:
#   "high"   -> auto-place, very confident
#   "medium" -> auto-place, log warning
#   "low"    -> auto-place, but flag for review
#   None     -> goes to _unmatched/
# ============================================================================

def categorize_by_keywords(product_name):
    """Hand-tuned keyword decision tree for unknown SKUs. Best-effort, not perfect.
       Edit the rules below if you want to tweak how new products get bucketed."""
    if not product_name:
        return None
    n = product_name.lower()

    # ----- Bathroom: Bathroom Furniture and Storage -----
    if "shower bench" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Shower Benches", "high")
    if ("shower caddy" in n or "shower organizer" in n or "suction holder" in n
            or "shower stand" in n or "shower shelf" in n):
        return ("Bathroom", "Bathroom Furniture and Storage",
                "Shower Organizers and Caddies", "high")
    if "floating" in n and ("shelf" in n or "shelves" in n):
        return ("Bathroom", "Bathroom Furniture and Storage",
                "Floating Wall Shelves", "high")
    if "wall shelf" in n or "wall shelves" in n:
        return ("Bathroom", "Bathroom Furniture and Storage",
                "Floating Wall Shelves", "medium")
    if "amenities tray" in n or "storage bin" in n:
        return ("Bathroom", "Bathroom Furniture and Storage",
                "Storage Bins and Trays", "high")
    if ("storage chest" in n or "storage box" in n or "storage cabinet" in n
            or "storage cup" in n):
        return ("Bathroom", "Bathroom Furniture and Storage", "Storage", "medium")
    if "shaving" in n or "foot rest" in n or "pedestal" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Shower Benches", "medium")
    if "bath stand" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Storage", "medium")

    # ----- Bathroom: Bath Accessories -----
    if ("bath mat" in n or "shower mat" in n or "bath & shower mat" in n
            or "bath and shower mat" in n):
        return ("Bathroom", "Bath Accessories", "Floor Mats", "high")
    if "hamper" in n:
        return ("Bathroom", "Bath Accessories", "Waste Baskets and Hampers", "high")
    if "waste basket" in n or "wastebasket" in n:
        return ("Bathroom", "Bath Accessories", "Waste Baskets and Hampers", "high")
    if "towel rack" in n or "towel stand" in n or "towel" in n:
        return ("Bathroom", "Bath Accessories", "Towel Racks", "high")
    if "side table" in n:
        return ("Bathroom", "Bath Accessories", "Side Tables", "high")

    # ----- Indoor: Kitchen -----
    if "knife" in n:
        return ("Indoor", "Kitchen", "Countertop Accessories", "high")
    if "anti-fatigue" in n and "mat" in n:
        return ("Indoor", "Kitchen", "Floor Mats", "high")
    if "bar stool" in n or "counter stool" in n:
        return ("Indoor", "Kitchen", "Bar and Counter Stools", "high")
    if "napkin" in n or "paper towel" in n:
        return ("Indoor", "Kitchen", "Countertop Accessories", "high")

    # ----- Indoor: Entryway / Living Room -----
    if "entryway bench" in n:
        return ("Indoor", "Entryway", "Entryway Benches", "high")
    if "coat stand" in n or "key holder" in n:
        return ("Indoor", "Entryway", "Key Holders", "medium")
    if "coffee table" in n:
        return ("Indoor", "Living Room", "Coffee Tables", "high")
    if "tissue" in n:
        return ("Indoor", "Living Room", "Tissue Boxes and Hangers", "high")
    if "step stool" in n:
        return ("Indoor", "Living Room", "Storage", "low")
    if "corner stool" in n or "petite stool" in n:
        return ("Bathroom", "Bath Accessories", "Side Tables", "low")

    # Generic fallbacks (low confidence)
    if "shower" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Shower Benches", "low")
    if "shelf" in n or "shelves" in n:
        return ("Bathroom", "Bathroom Furniture and Storage",
                "Floating Wall Shelves", "low")

    return None  # truly unknown -> _unmatched/

# ============================================================================
# Phase 4: process one product folder
# ============================================================================

def process_product(product_dir, output_dir, sku_map):
    """Process one [SKU] Name folder. Returns one of:
       'matched_ref', 'matched_keyword', 'matched_color',
       'unmatched_extracted' (couldn't categorize but extracted whiteshot to _unmatched/),
       'no_whiteshots' (nothing to do, source kept),
       'malformed', 'error'.

       On success / unmatched_extracted: copies best whiteshot, deletes source folder.
       On no_whiteshots / malformed / error: leaves source folder untouched."""
    folder_base = os.path.basename(product_dir.rstrip("/"))
    sku, local_name = parse_sku_folder(folder_base)

    if not sku:
        log.log_failure(
            sku="?", status="MALFORMED FOLDER",
            reason=f"folder name has no [SKU] prefix: {folder_base!r}",
            source_folder=product_dir,
        )
        return "malformed"

    # ---- find best white shot ----
    white_folders = find_white_folders(product_dir)
    files = []
    for wf in white_folders:
        files.extend(list_image_files(wf))

    if not files:
        log.log_failure(
            sku=sku, status="NO WHITESHOTS",
            reason=(f"no images found in any 'White*' folder under this product. "
                    f"Checked {len(white_folders)} matching folder(s)."),
            source_folder=product_dir,
            product_name=local_name,
            white_folders_found=white_folders or "(none matched)",
            hint="if this product has images elsewhere (e.g. only in Lifestyle/), "
                 "you'll need to handle it manually",
        )
        return "no_whiteshots"

    best = pick_best_whiteshot(files)
    src_fname, src_path = best

    # ---- decide category, in order ----
    via = None
    top = mid = gran = None
    product_name = local_name or sku
    out_sku = sku  # may get rewritten for color variants

    def _has_category(d):
        return all(k in d for k in ("top", "mid", "gran"))

    # 1. direct reference lookup (or override)
    ref_hit = sku_map.get(sku) if sku_map else None
    if ref_hit:
        top, mid, gran = ref_hit["top"], ref_hit["mid"], ref_hit["gran"]
        product_name = local_name or ref_hit["name"]
        via = "ref"
        status_label = "matched_ref"
    elif sku in SKU_OVERRIDES:
        ov = SKU_OVERRIDES[sku]
        # set name regardless of mode
        product_name = local_name or ov.get("name") or sku
        if _has_category(ov):
            top, mid, gran = ov["top"], ov["mid"], ov["gran"]
            via = "override"
            status_label = "matched_ref"
        # else: name-only - product_name set, fall through to keyword/unmatched

    # 2. color variant of a known base SKU (ref OR override)
    if not via:
        base_sku, color_abbrev, color_word = detect_color_variant(sku)
        if base_sku:
            base_hit = None
            base_source = None
            if sku_map and base_sku in sku_map:
                base_hit = sku_map[base_sku]
                base_source = "ref"
            elif base_sku in SKU_OVERRIDES:
                base_hit = SKU_OVERRIDES[base_sku]
                base_source = "override"
            if base_hit:
                out_sku = f"{base_sku}-{color_abbrev}"
                product_name = local_name or base_hit.get("name") or sku
                if _has_category(base_hit):
                    top, mid, gran = base_hit["top"], base_hit["mid"], base_hit["gran"]
                    via = f"color({base_source}):{color_word}->{color_abbrev}"
                    status_label = "matched_color"
                # else: name-only base, product_name set, fall through

    # 3. keyword on name
    if not via:
        guess = categorize_by_keywords(local_name)
        if guess:
            top, mid, gran, conf = guess
            via = f"keyword:{conf}"
            status_label = "matched_keyword"

    # 4. fallback: still has whiteshot, extract to _unmatched/, delete source
    if not via:
        top, mid, gran = "_unmatched", "", ""
        via = "unmatched"
        status_label = "unmatched_extracted"

    # ---- build destination path ----
    if top == "_unmatched":
        dest_dir = os.path.join(output_dir, "_unmatched")
    else:
        dest_dir = os.path.join(
            output_dir,
            sanitize_folder_name(top),
            sanitize_folder_name(mid),
            sanitize_folder_name(gran),
        )

    ext = os.path.splitext(src_fname)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    out_name = (f"[{out_sku}] {sanitize_filename(product_name)}{ext}"
                if product_name and product_name != out_sku
                else f"[{out_sku}]{ext}")
    out_path = os.path.join(dest_dir, out_name)

    if DRY_RUN:
        log.log_success(sku=out_sku, dest_category=f"{top}/{mid}/{gran}".rstrip("/"),
                        source_file=src_fname, dest_path=out_path + " (DRY RUN)",
                        via=via)
        return status_label

    # ---- copy ----
    try:
        os.makedirs(dest_dir, exist_ok=True)
        if os.path.exists(out_path):
            log.add("Output collision (overwriting)", out_sku, f"existing {out_path}")
        shutil.copy2(src_path, out_path)
    except Exception as e:
        log.log_failure(
            sku=sku, status="COPY ERROR",
            reason=f"failed to copy {src_path} -> {out_path}: {e}",
            source_folder=product_dir,
        )
        return "error"

    # ---- delete source folder on success ----
    if DELETE_AFTER_SORT:
        try:
            shutil.rmtree(product_dir)
        except Exception as e:
            log.add("Source delete failed (copy still succeeded)", out_sku,
                    f"{product_dir}: {e}")

    log.log_success(sku=out_sku, dest_category=f"{top}/{mid}/{gran}".rstrip("/"),
                    source_file=src_fname, dest_path=out_path, via=via)
    return status_label

# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 70)
    print("Extract White Shots (1 best file per product)")
    print("=" * 70)
    print(f"  Input:     {INPUT_TREE}")
    print(f"  Reference: {REFERENCE_TREE}")
    print(f"  Output:    {OUTPUT_DIR}")
    print(f"  Delete source on success: {DELETE_AFTER_SORT}")
    print(f"  Dry run:                  {DRY_RUN}")
    print("=" * 70 + "\n")

    if not os.path.isdir(INPUT_TREE):
        info(f"X Input folder doesn't exist: {INPUT_TREE}")
        sys.exit(1)
    if not os.path.isdir(REFERENCE_TREE):
        info(f"X Reference folder doesn't exist: {REFERENCE_TREE}")
        sys.exit(1)

    os.makedirs(LOG_FOLDER, exist_ok=True)
    sku_map = build_sku_map_from_reference(REFERENCE_TREE)
    if not sku_map:
        info("X Could not build SKU map. Aborting.")
        sys.exit(1)

    product_dirs = sorted(
        os.path.join(INPUT_TREE, e) for e in os.listdir(INPUT_TREE)
        if os.path.isdir(os.path.join(INPUT_TREE, e))
    )
    info(f"\nFound {len(product_dirs)} product folders to process\n")

    counts = defaultdict(int)
    if not DRY_RUN:
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    for pd in tqdm(product_dirs, desc="Products", unit="prod"):
        try:
            status = process_product(pd, OUTPUT_DIR, sku_map)
            counts[status] += 1
        except Exception as e:
            log.log_failure(
                sku=os.path.basename(pd), status="UNEXPECTED ERROR",
                reason=str(e), source_folder=pd,
            )
            counts["error"] += 1

    sorted_count = (counts["matched_ref"] + counts["matched_keyword"]
                    + counts["matched_color"])
    extracted_unmatched = counts["unmatched_extracted"]
    failed_count = counts["no_whiteshots"] + counts["malformed"] + counts["error"]

    summary = {
        "Total product folders":           len(product_dirs),
        "  Sorted (source deleted)":       sorted_count,
        "      - via reference tree":      counts["matched_ref"],
        "      - via keyword":             counts["matched_keyword"],
        "      - via color variant":       counts["matched_color"],
        "  Extracted to _unmatched/":      extracted_unmatched,
        "  Left in place (manual)":        failed_count,
        "      - no whiteshots":           counts["no_whiteshots"],
        "      - malformed folder":        counts["malformed"],
        "      - errors":                  counts["error"],
        "SKUs in reference tree":          len(sku_map),
    }
    log.write(summary)

    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)
    for k, v in summary.items():
        print(f"  {k:<42} {v}")
    print(f"\n  Log: {LOG_FILE}")
    if extracted_unmatched:
        print(f"\n  (!) {extracted_unmatched} extracted to {OUTPUT_DIR}/_unmatched/ "
              f"- move into right category manually.")
    if failed_count:
        print(f"  (!) {failed_count} folder(s) left in {INPUT_TREE} for manual review.")

if __name__ == "__main__":
    main()