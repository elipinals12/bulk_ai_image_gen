#!/usr/bin/env python3
"""Rename [sku] folders to '[sku] product name' based on image filenames in inputs/run2."""
import os, re
from pathlib import Path

INPUTS = Path.home() / "Documents/bulkimgen/inputs/run2"
OUTPUTS = Path.home() / "Documents/bulkimgen/outputs/generated_images"
DRY_RUN = False  # flip to False to actually rename

# pattern: [sku] name.jpg  (sku may contain letters/digits/hyphens)
PATTERN = re.compile(r"^(\[[^\]]+\])\s+(.+)\.jpg$", re.IGNORECASE)

# 1. build sku -> name map from inputs tree
sku_map = {}
for jpg in INPUTS.rglob("*.jpg"):
    m = PATTERN.match(jpg.name)
    if not m:
        print(f"skip (no match): {jpg.name}")
        continue
    sku, name = m.group(1), m.group(2).strip()
    if sku in sku_map and sku_map[sku] != name:
        print(f"warn: {sku} has conflicting names: '{sku_map[sku]}' vs '{name}'")
    sku_map[sku] = name

print(f"\nfound {len(sku_map)} sku->name mappings\n")

# 2. rename folders in outputs
renamed = skipped = missing = 0
for folder in OUTPUTS.iterdir():
    if not folder.is_dir():
        continue
    # folder name might already be renamed; only touch pure [sku] folders
    if not re.fullmatch(r"\[[^\]]+\]", folder.name):
        skipped += 1
        continue
    sku = folder.name
    if sku not in sku_map:
        print(f"no name found for {sku}")
        missing += 1
        continue
    new_name = f"{sku} {sku_map[sku]}"
    # sanitize: strip chars illegal on most fs (keep it light, names look clean already)
    new_name = re.sub(r'[/\\:*?"<>|]', "_", new_name)
    target = folder.parent / new_name
    if target.exists():
        print(f"target exists, skip: {target.name}")
        skipped += 1
        continue
    print(f"{'[DRY]' if DRY_RUN else '[RUN]'} {folder.name}  ->  {new_name}")
    if not DRY_RUN:
        folder.rename(target)
    renamed += 1

print(f"\ndone. renamed={renamed} skipped={skipped} missing_name={missing}")
print("DRY_RUN was True — set to False to apply." if DRY_RUN else "applied.")