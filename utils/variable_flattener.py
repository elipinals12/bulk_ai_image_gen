import os
import shutil
from pathlib import Path
from collections import defaultdict

# ============ SETTINGS ============
SOURCE_FOLDER = "generated_images"
OUTPUT_FOLDER = "sorted_images_2_layers"
PRESERVE_DEPTH = 2  # 1 = keep first level (indoor/outdoor/bathroom), 0 = dump all files into one folder
DRY_RUN = False     # True = preview only, False = actually copy files
# ==================================

def flatten_to_depth(src_dir, dest_dir, preserve_depth, dry_run):
    src = Path(src_dir)
    dest = Path(dest_dir)
    
    if not src.exists():
        print(f"Error: Source directory '{src}' does not exist")
        return
    
    # Track files to handle name collisions
    file_counts = defaultdict(int)
    copied = 0
    
    for filepath in src.rglob('*'):
        if not filepath.is_file():
            continue
        
        # Get path relative to source
        rel_path = filepath.relative_to(src)
        parts = rel_path.parts
        
        # Build the preserved path (first N directories)
        if len(parts) > preserve_depth:
            preserved = Path(*parts[:preserve_depth])
        else:
            preserved = Path(*parts[:-1]) if len(parts) > 1 else Path('.')
        
        # Handle filename collisions by adding a counter
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
            shutil.copy2(filepath, dest_file)
        
        copied += 1
    
    action = "Would copy" if dry_run else "Copied"
    print(f"\n{action} {copied} files")


if __name__ == "__main__":
    print(f"Source: {SOURCE_FOLDER}")
    print(f"Output: {OUTPUT_FOLDER}")
    print(f"Preserving {PRESERVE_DEPTH} level(s) of folders")
    print(f"Mode: {'DRY RUN (preview)' if DRY_RUN else 'LIVE (copying files)'}\n")
    
    flatten_to_depth(SOURCE_FOLDER, OUTPUT_FOLDER, PRESERVE_DEPTH, DRY_RUN)