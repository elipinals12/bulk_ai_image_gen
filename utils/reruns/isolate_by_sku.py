#!/usr/bin/env python3
"""
Copy product folders matching a SKU list into a new folder.
Match rule: folder name must start with '[SKU]' (literal brackets).
"""

import os
import shutil
from pathlib import Path

# ---- CONFIG: edit these two paths ----
SOURCE_DIR = Path("/home/eli/Documents/bulkimgen/aquateak_products/full_db")
DEST_DIR   = Path("/home/eli/Documents/bulkimgen/inputs/run2")
# --------------------------------------

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

def main():
    # dedupe while preserving order
    seen = set()
    skus = [s for s in SKUS if not (s in seen or seen.add(s))]
    print(f"[info] {len(SKUS)} SKUs in list, {len(skus)} unique after dedupe")

    if not SOURCE_DIR.exists():
        print(f"[fatal] SOURCE_DIR does not exist: {SOURCE_DIR}")
        return
    if not SOURCE_DIR.is_dir():
        print(f"[fatal] SOURCE_DIR is not a directory: {SOURCE_DIR}")
        return

    if DEST_DIR.exists():
        try:
            shutil.rmtree(DEST_DIR)
            print(f"[info] wiped existing dest folder")
        except OSError as e:
            print(f"[fatal] cannot wipe DEST_DIR: {e}")
            return
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[info] copying into: {DEST_DIR}")

    # list source folders once
    try:
        entries = [p for p in SOURCE_DIR.iterdir() if p.is_dir()]
    except OSError as e:
        print(f"[fatal] cannot read SOURCE_DIR: {e}")
        return

    copied, skipped, errored, ambiguous = 0, [], [], []

    for sku in skus:
        prefix = f"[{sku}]"
        matches = [p for p in entries if p.name.startswith(prefix)]

        # fallback: search one level deep (handles nested variants like [190]/[190-BLACK])
        if not matches:
            for entry in entries:
                try:
                    for sub in entry.iterdir():
                        if sub.is_dir() and sub.name.startswith(prefix):
                            matches.append(sub)
                except OSError as e:
                    print(f"[warn] cannot read into '{entry.name}': {e}")

        if not matches:
            skipped.append(sku)
            print(f"[skip] product {sku} doesn't exist")
            continue

        if len(matches) > 1:
            ambiguous.append((sku, [m.name for m in matches]))
            print(f"[warn] multiple matches for '{prefix}': {[m.name for m in matches]} — copying all")

        for src in matches:
            dst = DEST_DIR / src.name
            if dst.exists():
                print(f"[skip] already exists in dest: {dst.name}")
                continue
            try:
                shutil.copytree(src, dst)
                copied += 1
            except (OSError, shutil.Error) as e:
                errored.append((src.name, str(e)))
                print(f"[err]  failed copying '{src.name}': {e}")

    print("\n===== summary =====")
    print(f"copied:    {copied}")
    print(f"skipped:   {len(skipped)} -> {skipped}")
    print(f"ambiguous: {len(ambiguous)} -> {ambiguous}")
    print(f"errors:    {len(errored)} -> {errored}")

if __name__ == "__main__":
    main()