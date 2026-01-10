import os, shutil

SRC = "generated_images"     # root with nested folders
DST = "all_generated"       # flat output folder

os.makedirs(DST, exist_ok=True)

img_ext = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff")

seen = {}

for root, _, files in os.walk(SRC):
    for f in files:
        if f.lower().endswith(img_ext):
            src_path = os.path.join(root, f)

            name, ext = os.path.splitext(f)
            count = seen.get(f, 0)
            seen[f] = count + 1

            new_name = f if count == 0 else f"{name}_{count}{ext}"
            dst_path = os.path.join(DST, new_name)

            shutil.copy2(src_path, dst_path)
