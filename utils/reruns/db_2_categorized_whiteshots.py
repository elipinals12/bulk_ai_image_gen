#!/usr/bin/env python3
"""
Whiteshot Pipeline (one-shot)
==============================
Combines isolate_by_sku.py + extract_whiteshots.py into a single task.

Flow per SKU in the SKUS list below:
  1. locate the product folder [SKU]* inside SOURCE_DIR (with 1-level nested fallback
     for color-variant sub-folders like [190]/[190-BLACK])
  2. find the best white shot inside it (WS #1_hq > WS #1 > lowest #N > first alphabetical)
  3. categorize: reference tree -> SKU_OVERRIDES -> color variant -> keyword -> _unmatched
  4. copy that one whiteshot into OUTPUT_DIR/<top>/<mid>/<gran>/[SKU] Name.jpg

Source folder is NEVER modified - read-only.

End of run:
  - terminal: high-level counts
  - logs/whiteshot_pipeline_log.txt: detailed per-SKU breakdown of every failure mode

Run:  python whiteshot_pipeline.py
"""

import os
import re
import sys
import json
import shutil
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    from tqdm import tqdm
except ImportError:
    # fallback if tqdm not installed - just iterate plainly
    def tqdm(it, **kw): return it

# ============================================================================
# CONFIG  (edit these paths/lists)
# ============================================================================

SOURCE_DIR     = Path("/home/eli/Documents/bulkimgen/aquateak_products/full_db")
REFERENCE_TREE = Path("/home/eli/Documents/bulkimgen/aquateak_products/old sorted")
OUTPUT_DIR     = Path("/home/eli/Documents/bulkimgen/aquateak_products/run2")

DRY_RUN        = False   # True = log only, no copies, no wipe
WIPE_OUTPUT    = True    # wipe OUTPUT_DIR before run for a fresh result

SKUS = [
    "100","103","107","108","109","129","134-N","144","160","177","183",
    "190-BLACK","190-BLUE","190-GREY","190-RED","190-WHITE","193","216","217","219","229",
    "230-M","237","238","239","240","241","242","243","244","245","246","247",
    "248","249","250","251","252","253","254","255","256","257","258","259",
    "260","261-D","262","263","264","265","266","267","268","269","270","272",
    "273","274","275","276","277","278","279","280","281","282","283","285",
    "289","292","293","294","295","297","304-N","321","334","335","344","380",
    "398","451","452","468-M","487-M","506","507","512","542","535","548","551",
    "552","553","224","573","636","637","638","641","657","663",
]

# ============================================================================
# MANUAL SKU OVERRIDES
# Two modes:
#   1. NAME ONLY   -> {"name": "..."}        sets filename, routes to _unmatched/
#   2. FULL        -> {"name", "top", "mid", "gran"}   auto-categorizes
# ============================================================================

SKU_OVERRIDES = {
    "190": {"name": "18 Asia Decorative Wood Bench"},  # name-only; color variants get name + _unmatched
    # "451": {"name": "Mesa Large Teak Lantern"},
    # "999": {"name": "Foo", "top": "Indoor", "mid": "Living Room", "gran": "Storage"},
}

# ============================================================================
# Constants
# ============================================================================

LOG_FOLDER     = Path("/home/eli/Documents/bulkimgen/logs")
LOG_FILE       = LOG_FOLDER / "whiteshot_pipeline_log.txt"
SKU_MAP_CACHE  = LOG_FOLDER / "sku_category_map.json"

WHITE_FOLDER_NAMES = {
    "white", "white background", "white shots", "whiteshots",
    "whites", "white shot", "ws",
}
SKIP_FOLDER_NAMES = {
    "360 view", "360", "lifestyle", "dimensions", "dimension",
    "drawings", "drawing", "raw", "picture", "gif",
}
IMG_EXTS = {".jpg", ".jpeg", ".png"}

COLOR_FULL_TO_ABBREV = {
    "BLACK": "B", "BLUE": "BL", "GREY": "G", "GRAY": "G",
    "RED": "R", "WHITE": "W", "GREEN": "GR", "BROWN": "BR",
}

SKU_FOLDER_RE       = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
LEGACY_FILENAME_RE  = re.compile(r"^([A-Za-z0-9\-_]+)\s*-\s*(.+)$")
SHOT_NUM_RE         = re.compile(r"(?:ws\s*#|#|\()\s*(\d+)", re.IGNORECASE)

# ============================================================================
# Logger
# ============================================================================

class Logger:
    """Buckets per-SKU outcomes so the final report is grouped and scannable."""
    def __init__(self):
        self.successes        = []   # [(sku, via, category, src_file, dest)]
        self.unmatched_extr   = []   # [(sku, src_file, dest)]  extracted to _unmatched/
        self.not_in_source    = []   # [sku, ...]  folder never found
        self.no_whiteshots    = []   # [(sku, folder, white_folders_found)]
        self.malformed        = []   # [(folder_name, reason)]
        self.copy_errors      = []   # [(sku, src, dst, error)]
        self.ambiguous        = []   # [(sku, [folder_names])]
        self.events           = defaultdict(list)   # bucket -> [(sku, msg)]

    def event(self, bucket, sku, msg):
        self.events[bucket].append((sku, msg))

    def write(self, summary):
        LOG_FOLDER.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            bar = "=" * 96
            sep = "-" * 96
            f.write(f"{bar}\nWHITESHOT PIPELINE - LOG\nTimestamp: {datetime.now():%Y-%m-%d %H:%M:%S}\n{bar}\n\n")

            f.write("SUMMARY\n" + sep + "\n")
            for k, v in summary.items():
                f.write(f"  {k:<46} {v}\n")
            f.write("\n")

            # ---------------- NEEDS YOUR ATTENTION ----------------
            critical = (self.not_in_source or self.no_whiteshots
                        or self.malformed or self.copy_errors)
            if critical:
                f.write(f"\n{bar}\nNEEDS YOUR ATTENTION\n{bar}\n\n")

                if self.not_in_source:
                    f.write(f"-- SKUs in your list but folder NOT FOUND in source ({len(self.not_in_source)}) --\n")
                    f.write("   (these SKUs may be typos, missing from full_db, or use a different folder-name format)\n\n")
                    for sku in sorted(self.not_in_source, key=_sku_sort_key):
                        f.write(f"   [{sku}]\n")
                    f.write("\n")

                if self.no_whiteshots:
                    f.write(f"-- Folder found but NO WHITESHOT inside ({len(self.no_whiteshots)}) --\n")
                    f.write("   (no 'White*' subfolder with images - may live under Lifestyle/, Raw/, etc - handle manually)\n\n")
                    for sku, folder, wfs in sorted(self.no_whiteshots, key=lambda x: _sku_sort_key(x[0])):
                        f.write(f"   [{sku}]  {folder}\n")
                        f.write(f"        white folders found: {wfs or '(none)'}\n")
                    f.write("\n")

                if self.malformed:
                    f.write(f"-- Folders with malformed names (no [SKU] prefix) ({len(self.malformed)}) --\n\n")
                    for name, reason in self.malformed:
                        f.write(f"   {name}\n        {reason}\n")
                    f.write("\n")

                if self.copy_errors:
                    f.write(f"-- COPY ERRORS ({len(self.copy_errors)}) --\n\n")
                    for sku, src, dst, err in self.copy_errors:
                        f.write(f"   [{sku}]\n        src: {src}\n        dst: {dst}\n        err: {err}\n\n")

            # ---------------- REVIEW: EXTRACTED BUT UNCATEGORIZED ----------------
            if self.unmatched_extr:
                f.write(f"\n{bar}\nREVIEW: extracted to _unmatched/ ({len(self.unmatched_extr)})\n")
                f.write("(whiteshot WAS copied - just couldn't auto-pick a category. Move manually inside OUTPUT_DIR/_unmatched/)\n")
                f.write(f"{bar}\n\n")
                for sku, src, dst in sorted(self.unmatched_extr, key=lambda x: _sku_sort_key(x[0])):
                    f.write(f"   [{sku}]  picked: {src}\n        -> {dst}\n")
                f.write("\n")

            # ---------------- AMBIGUOUS ----------------
            if self.ambiguous:
                f.write(f"\n{bar}\nAMBIGUOUS MATCHES ({len(self.ambiguous)})  -- multiple folders matched one SKU; all processed\n{bar}\n\n")
                for sku, names in sorted(self.ambiguous, key=lambda x: _sku_sort_key(x[0])):
                    f.write(f"   [{sku}]\n")
                    for n in names:
                        f.write(f"        - {n}\n")
                f.write("\n")

            # ---------------- SUCCESSES ----------------
            if self.successes:
                f.write(f"\n{bar}\nSUCCESSFULLY SORTED  ({len(self.successes)})\n{bar}\n\n")
                for sku, via, cat, src, dst in sorted(self.successes, key=lambda x: _sku_sort_key(x[0])):
                    f.write(f"   [{sku}]  via {via:<22}  -> {cat}\n        (picked: {src})\n")
                f.write("\n")

            # ---------------- EXTRA EVENTS ----------------
            if self.events:
                f.write(f"\n{bar}\nADDITIONAL EVENTS (debug)\n{bar}\n\n")
                for bucket in sorted(self.events):
                    f.write(f"\n{bucket}  ({len(self.events[bucket])})\n{sep}\n")
                    for sku, msg in self.events[bucket]:
                        f.write(f"   [{sku}] {msg}\n")

log = Logger()

def info(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")

def _sku_sort_key(sku):
    m = re.match(r"(\d+)(.*)", sku)
    return (int(m.group(1)), m.group(2)) if m else (10**9, sku)

# ============================================================================
# Sanitization
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
# Parsing helpers
# ============================================================================

def parse_sku_folder(folder_basename):
    """'[100] 18 Asia...' -> ('100', '18 Asia...'). '[190-BLACK]' -> ('190-BLACK', '')."""
    m = SKU_FOLDER_RE.match(folder_basename.strip())
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()

def parse_reference_filename(fname):
    """'100 - Slatted Bench.jpg' OR '[100] Slatted Bench.jpg' -> ('100', 'Slatted Bench')."""
    stem, _ = os.path.splitext(fname)
    m_new = SKU_FOLDER_RE.match(stem.strip())
    if m_new:
        return m_new.group(1).strip(), (m_new.group(2).strip() or m_new.group(1).strip())
    m_old = LEGACY_FILENAME_RE.match(stem.strip())
    if m_old:
        return m_old.group(1).strip(), m_old.group(2).strip()
    return None, None

def detect_color_variant(sku):
    """'190-BLACK' -> ('190', 'B', 'BLACK').  '100' -> (None, None, None)."""
    if "-" not in sku:
        return None, None, None
    base, _, suffix = sku.rpartition("-")
    suffix_u = suffix.upper()
    if suffix_u in COLOR_FULL_TO_ABBREV:
        return base, COLOR_FULL_TO_ABBREV[suffix_u], suffix_u
    return None, None, None

# ============================================================================
# Phase 1: build SKU -> category map from reference tree
# ============================================================================

def build_sku_map_from_reference(ref_root: Path):
    """Walk ref_root/{top}/{mid}/{gran}/{file}, return {sku: {top, mid, gran, name}}."""
    if not ref_root.is_dir():
        info(f"X Reference tree not found: {ref_root}")
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
                log.event("Reference: unparseable filename", "?", f"{dirpath}/{fname}")
                skipped += 1
                continue
            if sku in sku_map:
                ex = sku_map[sku]
                if (ex["top"], ex["mid"], ex["gran"]) != (top, mid, gran):
                    log.event("Reference: SKU in multiple categories", sku,
                              f"keeping {ex['top']}/{ex['mid']}/{ex['gran']}; ignoring {top}/{mid}/{gran}")
                continue
            sku_map[sku] = {"top": top, "mid": mid, "gran": gran, "name": name}

    info(f"  -> {files_seen} files scanned, {len(sku_map)} unique SKUs ({skipped} unparseable)")
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    with open(SKU_MAP_CACHE, "w") as f:
        json.dump(sku_map, f, indent=2)
    info(f"  -> Cached to {SKU_MAP_CACHE}")
    return sku_map

# ============================================================================
# Phase 2: find product folders in SOURCE_DIR for a given SKU
# ============================================================================

def find_source_folders_for_sku(sku, top_level_entries):
    """Search SOURCE_DIR for folders whose name starts with '[SKU]'.
       Falls back to looking 1 level deep (handles nested color variants).
       Returns list of Path objects (may be empty)."""
    prefix = f"[{sku}]"
    matches = [p for p in top_level_entries if p.name.startswith(prefix)]
    if matches:
        return matches

    # nested fallback - 1 level deep
    nested = []
    for entry in top_level_entries:
        try:
            for sub in entry.iterdir():
                if sub.is_dir() and sub.name.startswith(prefix):
                    nested.append(sub)
        except OSError as e:
            log.event("Cannot read subfolder", sku, f"{entry.name}: {e}")
    return nested

# ============================================================================
# Phase 3: find white shots and pick the best one
# ============================================================================

def find_white_folders(product_root: Path):
    """Recursively find all whitelisted 'white*' folders inside product_root."""
    matches = []
    for dirpath, dirnames, _ in os.walk(product_root):
        dirnames[:] = [d for d in dirnames if d.strip().lower() not in SKIP_FOLDER_NAMES]
        if os.path.basename(dirpath).strip().lower() in WHITE_FOLDER_NAMES:
            matches.append(dirpath)
    return matches

def list_image_files(folder):
    out = []
    try:
        for entry in os.listdir(folder):
            full = os.path.join(folder, entry)
            if os.path.isfile(full) and os.path.splitext(entry)[1].lower() in IMG_EXTS:
                out.append((entry, full))
    except OSError as e:
        log.event("Cannot list folder", "?", f"{folder}: {e}")
    return out

def pick_best_whiteshot(files):
    """Score: (shot_number, hq_penalty, fname). Lower wins."""
    if not files:
        return None
    if len(files) == 1:
        return files[0]

    def score(item):
        fname = item[0].lower()
        m = SHOT_NUM_RE.search(fname)
        shot_num = int(m.group(1)) if m else 999
        is_hq = "_hq" in fname
        return (shot_num, 0 if is_hq else 1, fname)

    return sorted(files, key=score)[0]

# ============================================================================
# Phase 4: keyword categorization for unknown SKUs
# ============================================================================

def categorize_by_keywords(product_name):
    """Hand-tuned keyword tree. Returns (top, mid, gran, confidence) or None."""
    if not product_name:
        return None
    n = product_name.lower()

    # Bathroom: Bathroom Furniture and Storage
    if "shower bench" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Shower Benches", "high")
    if ("shower caddy" in n or "shower organizer" in n or "suction holder" in n
            or "shower stand" in n or "shower shelf" in n):
        return ("Bathroom", "Bathroom Furniture and Storage", "Shower Organizers and Caddies", "high")
    if "floating" in n and ("shelf" in n or "shelves" in n):
        return ("Bathroom", "Bathroom Furniture and Storage", "Floating Wall Shelves", "high")
    if "wall shelf" in n or "wall shelves" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Floating Wall Shelves", "medium")
    if "amenities tray" in n or "storage bin" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Storage Bins and Trays", "high")
    if ("storage chest" in n or "storage box" in n or "storage cabinet" in n
            or "storage cup" in n):
        return ("Bathroom", "Bathroom Furniture and Storage", "Storage", "medium")
    if "shaving" in n or "foot rest" in n or "pedestal" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Shower Benches", "medium")
    if "bath stand" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Storage", "medium")

    # Bathroom: Bath Accessories
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

    # Indoor: Kitchen
    if "knife" in n:
        return ("Indoor", "Kitchen", "Countertop Accessories", "high")
    if "anti-fatigue" in n and "mat" in n:
        return ("Indoor", "Kitchen", "Floor Mats", "high")
    if "bar stool" in n or "counter stool" in n:
        return ("Indoor", "Kitchen", "Bar and Counter Stools", "high")
    if "napkin" in n or "paper towel" in n:
        return ("Indoor", "Kitchen", "Countertop Accessories", "high")

    # Indoor: Entryway / Living Room
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

    # Generic fallbacks
    if "shower" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Shower Benches", "low")
    if "shelf" in n or "shelves" in n:
        return ("Bathroom", "Bathroom Furniture and Storage", "Floating Wall Shelves", "low")

    return None

# ============================================================================
# Phase 5: process one (sku, folder) pair
# ============================================================================

def process_folder(requested_sku, product_dir: Path, sku_map):
    """For one matched product folder, find best whiteshot, categorize, copy.
       Returns one of:
         'matched_ref' | 'matched_override' | 'matched_color' | 'matched_keyword'
         | 'unmatched_extracted' | 'no_whiteshots' | 'malformed' | 'error'
    """
    folder_base = product_dir.name
    folder_sku, local_name = parse_sku_folder(folder_base)

    if not folder_sku:
        log.malformed.append((folder_base, "folder name has no [SKU] prefix"))
        return "malformed"

    # Find white shots
    white_folders = find_white_folders(product_dir)
    files = []
    for wf in white_folders:
        files.extend(list_image_files(wf))

    if not files:
        log.no_whiteshots.append((folder_sku, str(product_dir),
                                  [str(w) for w in white_folders]))
        return "no_whiteshots"

    best = pick_best_whiteshot(files)
    src_fname, src_path = best

    # ---- Categorization in order: ref -> override -> color -> keyword -> unmatched ----
    via = None
    top = mid = gran = None
    product_name = local_name or folder_sku
    out_sku = folder_sku

    def _has_cat(d): return all(k in d for k in ("top", "mid", "gran"))

    # 1. reference tree
    ref_hit = sku_map.get(folder_sku) if sku_map else None
    if ref_hit:
        top, mid, gran = ref_hit["top"], ref_hit["mid"], ref_hit["gran"]
        product_name = local_name or ref_hit["name"]
        via = "ref"
        status = "matched_ref"

    # 2. direct override
    elif folder_sku in SKU_OVERRIDES:
        ov = SKU_OVERRIDES[folder_sku]
        product_name = local_name or ov.get("name") or folder_sku
        if _has_cat(ov):
            top, mid, gran = ov["top"], ov["mid"], ov["gran"]
            via = "override"
            status = "matched_override"

    # 3. color variant of known base
    if not via:
        base_sku, color_abbrev, color_word = detect_color_variant(folder_sku)
        if base_sku:
            base_hit, base_src = None, None
            if sku_map and base_sku in sku_map:
                base_hit, base_src = sku_map[base_sku], "ref"
            elif base_sku in SKU_OVERRIDES:
                base_hit, base_src = SKU_OVERRIDES[base_sku], "override"
            if base_hit:
                out_sku = f"{base_sku}-{color_abbrev}"
                product_name = local_name or base_hit.get("name") or folder_sku
                if _has_cat(base_hit):
                    top, mid, gran = base_hit["top"], base_hit["mid"], base_hit["gran"]
                    via = f"color({base_src}):{color_word}->{color_abbrev}"
                    status = "matched_color"

    # 4. keyword on name
    if not via:
        guess = categorize_by_keywords(local_name)
        if guess:
            top, mid, gran, conf = guess
            via = f"keyword:{conf}"
            status = "matched_keyword"

    # 5. fallback: extracted but uncategorized
    if not via:
        top, mid, gran = "_unmatched", "", ""
        via = "unmatched"
        status = "unmatched_extracted"

    # ---- build dest path ----
    if top == "_unmatched":
        dest_dir = OUTPUT_DIR / "_unmatched"
    else:
        dest_dir = (OUTPUT_DIR / sanitize_folder_name(top)
                    / sanitize_folder_name(mid) / sanitize_folder_name(gran))

    ext = os.path.splitext(src_fname)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if product_name and product_name != out_sku:
        out_name = f"[{out_sku}] {sanitize_filename(product_name)}{ext}"
    else:
        out_name = f"[{out_sku}]{ext}"
    out_path = dest_dir / out_name

    if DRY_RUN:
        cat_str = f"{top}/{mid}/{gran}".rstrip("/")
        if status == "unmatched_extracted":
            log.unmatched_extr.append((out_sku, src_fname, f"{out_path} (DRY RUN)"))
        else:
            log.successes.append((out_sku, via, cat_str, src_fname, f"{out_path} (DRY RUN)"))
        return status

    # ---- copy ----
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            log.event("Output collision (overwriting)", out_sku, str(out_path))
        shutil.copy2(src_path, out_path)
    except Exception as e:
        log.copy_errors.append((out_sku, src_path, str(out_path), str(e)))
        return "error"

    cat_str = f"{top}/{mid}/{gran}".rstrip("/")
    if status == "unmatched_extracted":
        log.unmatched_extr.append((out_sku, src_fname, str(out_path)))
    else:
        log.successes.append((out_sku, via, cat_str, src_fname, str(out_path)))
    return status

# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 78)
    print("WHITESHOT PIPELINE  (single-shot: full_db -> categorized output)")
    print("=" * 78)
    print(f"  Source (READ-ONLY): {SOURCE_DIR}")
    print(f"  Reference tree:     {REFERENCE_TREE}")
    print(f"  Output:             {OUTPUT_DIR}")
    print(f"  Log file:           {LOG_FILE}")
    print(f"  SKUs requested:     {len(SKUS)}")
    print(f"  Wipe output first:  {WIPE_OUTPUT}")
    print(f"  Dry run:            {DRY_RUN}")
    print("=" * 78 + "\n")

    # ---- sanity ----
    if not SOURCE_DIR.is_dir():
        info(f"X SOURCE_DIR not found: {SOURCE_DIR}")
        sys.exit(1)
    if not REFERENCE_TREE.is_dir():
        info(f"X REFERENCE_TREE not found: {REFERENCE_TREE}")
        sys.exit(1)

    # ---- safety: never let OUTPUT_DIR overlap SOURCE_DIR ----
    src_res = SOURCE_DIR.resolve()
    out_res = OUTPUT_DIR.resolve()
    if out_res == src_res or src_res in out_res.parents or out_res in src_res.parents:
        info(f"X REFUSING TO RUN: OUTPUT_DIR ({out_res}) overlaps SOURCE_DIR ({src_res})")
        sys.exit(1)

    LOG_FOLDER.mkdir(parents=True, exist_ok=True)

    # ---- wipe output dir if requested ----
    if WIPE_OUTPUT and not DRY_RUN and OUTPUT_DIR.exists():
        try:
            shutil.rmtree(OUTPUT_DIR)
            info(f"Wiped existing OUTPUT_DIR for fresh run: {OUTPUT_DIR}")
        except OSError as e:
            info(f"X Cannot wipe OUTPUT_DIR: {e}")
            sys.exit(1)

    if not DRY_RUN:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- dedupe SKUs ----
    seen = set()
    skus = [s for s in SKUS if not (s in seen or seen.add(s))]
    if len(skus) != len(SKUS):
        info(f"Deduped SKU list: {len(SKUS)} -> {len(skus)}")

    # ---- build reference SKU->category map ----
    sku_map = build_sku_map_from_reference(REFERENCE_TREE)
    if sku_map is None:
        info("X Could not build reference SKU map. Aborting.")
        sys.exit(1)
    print()

    # ---- list source top-level entries once ----
    try:
        top_entries = [p for p in SOURCE_DIR.iterdir() if p.is_dir()]
    except OSError as e:
        info(f"X cannot read SOURCE_DIR: {e}")
        sys.exit(1)
    info(f"Source has {len(top_entries)} top-level folders. Processing {len(skus)} SKUs...\n")

    # ---- iterate SKU list ----
    counts = defaultdict(int)
    for sku in tqdm(skus, desc="SKUs", unit="sku"):
        matches = find_source_folders_for_sku(sku, top_entries)
        if not matches:
            log.not_in_source.append(sku)
            counts["not_in_source"] += 1
            continue

        if len(matches) > 1:
            log.ambiguous.append((sku, [m.name for m in matches]))

        for folder in matches:
            try:
                status = process_folder(sku, folder, sku_map)
                counts[status] += 1
            except Exception as e:
                log.copy_errors.append((sku, str(folder), "(processing)", repr(e)))
                counts["error"] += 1

    # ---- summary ----
    sorted_count = (counts["matched_ref"] + counts["matched_override"]
                    + counts["matched_color"] + counts["matched_keyword"])
    summary = {
        "SKUs requested (after dedupe)":     len(skus),
        "  - folder not found in source":    counts["not_in_source"],
        "  - folder found, no whiteshot":    counts["no_whiteshots"],
        "  - malformed folder name":         counts["malformed"],
        "  - copy errors":                   counts["error"],
        "  - extracted to _unmatched/":      counts["unmatched_extracted"],
        "  - sorted (categorized)":          sorted_count,
        "      via reference tree":          counts["matched_ref"],
        "      via SKU_OVERRIDES":           counts["matched_override"],
        "      via color variant":           counts["matched_color"],
        "      via keyword":                 counts["matched_keyword"],
        "Ambiguous matches":                 len(log.ambiguous),
        "Reference tree SKUs loaded":        len(sku_map),
    }
    log.write(summary)

    print("\n" + "=" * 78)
    print("DONE")
    print("=" * 78)
    for k, v in summary.items():
        print(f"  {k:<44} {v}")
    print(f"\n  Full report: {LOG_FILE}")

    if log.not_in_source:
        print(f"\n  (!) {len(log.not_in_source)} SKU(s) NOT FOUND in source - check log")
    if log.no_whiteshots:
        print(f"  (!) {len(log.no_whiteshots)} folder(s) had no whiteshot - check log")
    if counts["unmatched_extracted"]:
        print(f"  (!) {counts['unmatched_extracted']} extracted to {OUTPUT_DIR}/_unmatched/ - move manually")
    if log.copy_errors:
        print(f"  (!) {len(log.copy_errors)} copy error(s) - check log")

if __name__ == "__main__":
    main()