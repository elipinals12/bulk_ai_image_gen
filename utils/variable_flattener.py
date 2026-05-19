import os
import shutil
from pathlib import Path
from collections import defaultdict

# ============ SETTINGS ============
SOURCE_FOLDER = "../outputs/generated_images"
OUTPUT_FOLDER = "../outputs/sku_sorted"
PRESERVE_FROM_END = True   # True = keep last N levels, False = keep first N levels
PRESERVE_DEPTH = 1         # 1 from end = just the SKU folder
DRY_RUN = False            # True = preview only, False = actually copy files
# ==================================

def flatten_to_depth(src_dir, dest_dir, preserve_depth, preserve_from_end, dry_run):
    src = Path(src_dir)
    dest = Path(dest_dir)

    if not src.exists():
        print(f"Error: Source directory '{src}' does not exist")
        return

    file_counts = defaultdict(int)
    copied = 0

    for filepath in src.rglob('*'):
        if not filepath.is_file():
            continue

        rel_path = filepath.relative_to(src)
        parts = rel_path.parts  # e.g. ('bathroom', 'sub', 'subsub', 'SKU123', 'image.jpg')

        if preserve_from_end:
            # Keep last N directory levels (excluding the filename itself)
            dir_parts = parts[:-1]
            if len(dir_parts) > preserve_depth:
                preserved = Path(*dir_parts[-preserve_depth:])
            else:
                preserved = Path(*dir_parts) if dir_parts else Path('.')
        else:
            if len(parts) > preserve_depth:
                preserved = Path(*parts[:preserve_depth])
            else:
                preserved = Path(*parts[:-1]) if len(parts) > 1 else Path('.')

        filename = filepath.name
        dest_folder = dest / preserved
        dest_file = dest_folder / filename

        if dest_file.exists() or file_counts[(preserved, filename)] > 0:
            stem = filepath.stem
            suffix = filepath.suffix
            count = file_counts[(preserved, filename)]
            filename = f"{stem}_{count}{suffix}"
            dest_file = dest_folder / filename

        file_counts[(preserved, filepath.name)] += 1

        if dry_run:
            print(f"{filepath} -> {dest_file}")
        else:
            dest_folder.mkdir(parents=True, exist_ok=True)
            (dest_folder / "bad").mkdir(exist_ok=True)
            shutil.copy2(filepath, dest_file)

        copied += 1

    action = "Would copy" if dry_run else "Copied"
    print(f"\n{action} {copied} files")


if __name__ == "__main__":
    direction = "from end" if PRESERVE_FROM_END else "from start"
    print(f"Source: {SOURCE_FOLDER}")
    print(f"Output: {OUTPUT_FOLDER}")
    print(f"Preserving {PRESERVE_DEPTH} level(s) {direction}")
    print(f"Mode: {'DRY RUN (preview)' if DRY_RUN else 'LIVE (copying files)'}\n")

    flatten_to_depth(SOURCE_FOLDER, OUTPUT_FOLDER, PRESERVE_DEPTH, PRESERVE_FROM_END, DRY_RUN)