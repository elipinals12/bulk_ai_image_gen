"""
Extract Alpha Maps from C++ Header File
Parses embedded_assets.hpp and extracts PNG files for watermark removal.
"""

import re

def extract_byte_array(hpp_content, array_name):
    """
    Extract byte array data from C++ header file.
    
    Args:
        hpp_content: Content of the .hpp file as string
        array_name: Name of the array to extract (e.g., 'bg_48_png')
    
    Returns:
        bytes: Extracted PNG data
    """
    # Find the array declaration
    pattern = rf'{array_name}\[\]\s*=\s*{{([^}}]+)}};'
    match = re.search(pattern, hpp_content, re.DOTALL)
    
    if not match:
        raise ValueError(f"Could not find array '{array_name}' in header file")
    
    # Extract hex values
    hex_data = match.group(1)
    
    # Parse all hex values (0xNN format)
    hex_values = re.findall(r'0x([0-9a-fA-F]{2})', hex_data)
    
    # Convert to bytes
    byte_data = bytes([int(h, 16) for h in hex_values])
    
    return byte_data


def main():
    """Extract PNG files from embedded_assets.hpp"""
    
    hpp_file = "embedded_assets.hpp"
    
    print(f"Reading {hpp_file}...")
    
    try:
        with open(hpp_file, 'r') as f:
            hpp_content = f.read()
    except FileNotFoundError:
        print(f"❌ ERROR: {hpp_file} not found")
        print("Place embedded_assets.hpp in the same directory as this script")
        return
    
    # Extract bg_48.png
    print("Extracting bg_48.png...")
    try:
        bg_48_data = extract_byte_array(hpp_content, 'bg_48_png')
        with open('bg_48.png', 'wb') as f:
            f.write(bg_48_data)
        print(f"✓ Created bg_48.png ({len(bg_48_data)} bytes)")
    except Exception as e:
        print(f"❌ Failed to extract bg_48.png: {e}")
    
    # Extract bg_96.png
    print("Extracting bg_96.png...")
    try:
        bg_96_data = extract_byte_array(hpp_content, 'bg_96_png')
        with open('bg_96.png', 'wb') as f:
            f.write(bg_96_data)
        print(f"✓ Created bg_96.png ({len(bg_96_data)} bytes)")
    except Exception as e:
        print(f"❌ Failed to extract bg_96.png: {e}")
    
    print("\n✓ Alpha maps extracted successfully!")
    print("You can now run generate_images.py")


if __name__ == "__main__":
    main()
