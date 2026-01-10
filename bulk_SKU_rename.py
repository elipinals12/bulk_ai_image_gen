from pathlib import Path

root = Path("aquateak_products")

for path in root.rglob("*"):
    if path.is_file():
        name = path.stem
        ext = path.suffix

        if " - " in name:
            sku = name.split(" - ", 1)[0]
            new_path = path.with_name(sku + ext)

            if new_path != path:
                path.rename(new_path)
