"""
Product Image Scraper
Scrapes product images with white backgrounds, organizes by category, 
and prepares for AI image generation workflow.
"""

import os
import re
import time
import json
import shutil
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
from tqdm import tqdm

# ============================================================================
# Configuration
# ============================================================================

# Base URL for product listings
BASE_URL = "https://aquateak.com/all-1/"
TOTAL_PAGES = 7

# Output directory for downloaded images
OUTPUT_DIR = "aquateak_products"

# Log file for errors and skipped products
LOG_FILE = "scraper_log.txt"

# Category configuration file
CATEGORY_CONFIG = "category_prompts.json"

# White background detection settings
WHITE_THRESHOLD = 235  # RGB value threshold (0-255) - lowered to catch light grey backgrounds
WHITE_PERCENTAGE = 0.85  # 85% of sampled pixels must be white (allows for edge artifacts)
SAMPLE_INTERVAL = 20  # Sample every N pixels along perimeter

# Request delay to avoid rate limiting (seconds)
REQUEST_DELAY = 0.5

# ============================================================================
# Helper Functions
# ============================================================================

def log_skip(console_msg, log_msg):
    """Log skip/error message to console and log file separately"""
    # tqdm.write prints without disrupting progress bar
    tqdm.write(f"  {console_msg}")
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{log_msg}\n")
    except Exception as e:
        tqdm.write(f"  Warning: Couldn't write to log file: {e}")


def load_categories():
    """Load category configuration from JSON file"""
    try:
        with open(CATEGORY_CONFIG, 'r') as f:
            config = json.load(f)
            return config['categories']
    except Exception as e:
        print(f"Error loading categories from {CATEGORY_CONFIG}: {e}")
        print("Using fallback category configuration")
        return {
            'other': {'keywords': [], 'prompt': 'Default setting'}
        }


def sanitize_filename(name):
    """Remove or replace characters that are invalid in filenames"""
    # Replace inch symbol and other problematic characters
    name = name.replace('"', ' inch')
    name = name.replace('/', '-')
    name = name.replace('\\', '-')
    name = name.replace(':', '-')
    name = name.replace('*', '')
    name = name.replace('?', '')
    name = name.replace('<', '')
    name = name.replace('>', '')
    name = name.replace('|', '')
    name = name.replace('™', '')
    name = name.replace('®', '')
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name


def get_category(product_name, categories):
    """Match product name to category based on keywords (first match wins)"""
    product_lower = product_name.lower()
    
    for category_name, category_data in categories.items():
        for keyword in category_data['keywords']:
            if keyword in product_lower:
                return category_name
    
    return 'other'  # Fallback


def is_white_background(image_path, product_name, sku):
    """Check if image has white background by sampling perimeter pixels"""
    try:
        img = Image.open(image_path).convert('RGB')
        width, height = img.size
        
        samples = []
        
        # Sample top edge
        for x in range(0, width, SAMPLE_INTERVAL):
            samples.append(img.getpixel((x, 0)))
        
        # Sample bottom edge
        for x in range(0, width, SAMPLE_INTERVAL):
            samples.append(img.getpixel((x, height - 1)))
        
        # Sample left edge
        for y in range(0, height, SAMPLE_INTERVAL):
            samples.append(img.getpixel((0, y)))
        
        # Sample right edge
        for y in range(0, height, SAMPLE_INTERVAL):
            samples.append(img.getpixel((width - 1, y)))
        
        # Count how many samples are white enough
        white_count = sum(
            1 for r, g, b in samples 
            if r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD
        )
        
        white_ratio = white_count / len(samples)
        is_white = white_ratio >= WHITE_PERCENTAGE
        
        if not is_white:
            console_msg = f"!!! SKIP - BACKGROUND TOO DARK !!! White pixels: {white_ratio*100:.1f}% (needs {WHITE_PERCENTAGE*100:.1f}%)"
            log_msg = f"{sku} - {product_name}: Background too dark - {white_ratio*100:.1f}% white (needs {WHITE_PERCENTAGE*100:.1f}%)"
            log_skip(console_msg, log_msg)
        
        return is_white
        
    except Exception as e:
        console_msg = f"!!! SKIP - ERROR CHECKING BACKGROUND !!! {e}"
        log_msg = f"{sku} - {product_name}: Error checking background - {e}"
        log_skip(console_msg, log_msg)
        return False


def get_largest_image_url(soup):
    """Extract the largest available product image URL from product page"""
    # Try multiple selectors to handle different page structures
    
    # Method 1: Main product image
    img_tag = soup.select_one('.productView-image img')
    if img_tag:
        src = img_tag.get('src', '') or img_tag.get('data-src', '')
        if src:
            return re.sub(r'/\d+x\d+/', '/1280x1280/', src)
    
    # Method 2: Look for data-zoom-image attribute (for zoomable images)
    zoom_img = soup.select_one('[data-zoom-image]')
    if zoom_img:
        src = zoom_img.get('data-zoom-image', '')
        if src:
            return src
    
    # Method 3: Look for data-image or data-src attributes
    data_img = soup.select_one('[data-image], [data-src]')
    if data_img:
        src = data_img.get('data-image', '') or data_img.get('data-src', '')
        if src:
            return re.sub(r'/\d+x\d+/', '/1280x1280/', src)
    
    # Method 4: First image in product gallery
    gallery_img = soup.select_one('.productView-images img, .product-image img')
    if gallery_img:
        src = gallery_img.get('src', '') or gallery_img.get('data-src', '')
        if src:
            return re.sub(r'/\d+x\d+/', '/1280x1280/', src)
    
    return None


def fetch_page(url):
    """Fetch HTML content from URL with error handling"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def scrape_listing_page(page_num):
    """Scrape single listing page for product names and URLs"""
    url = f"{BASE_URL}?page={page_num}"
    
    html = fetch_page(url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    
    # Find all product cards
    product_cards = soup.select('.product')
    
    for card in product_cards:
        # Get product name from heading
        name_tag = card.select_one('.card-title a')
        if not name_tag:
            continue
        
        product_name = name_tag.get_text(strip=True)
        product_url = name_tag['href']
        
        # Make URL absolute
        if not product_url.startswith('http'):
            product_url = f"https://aquateak.com{product_url}"
        
        products.append({
            'name': product_name,
            'url': product_url
        })
    
    return products


def scrape_product_details(product):
    """Visit individual product page to get SKU and image URL"""
    time.sleep(REQUEST_DELAY)
    
    html = fetch_page(product['url'])
    if not html:
        console_msg = "!!! SKIP - COULDN'T FETCH PRODUCT PAGE !!!"
        log_msg = f"UNKNOWN - {product['name']}: Couldn't fetch product page"
        log_skip(console_msg, log_msg)
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract SKU
    sku_element = soup.find('dt', string='SKU:')
    if sku_element:
        sku_dd = sku_element.find_next_sibling('dd')
        if sku_dd:
            product['sku'] = sku_dd.get_text(strip=True)
    
    # Get largest image URL
    product['image_url'] = get_largest_image_url(soup)
    
    return product


def download_image(product, category_folder):
    """Download product image and save with proper filename"""
    sku = product.get('sku', 'UNKNOWN')
    product_name = product['name']
    
    if not product.get('image_url'):
        console_msg = "!!! SKIP - NO IMAGE URL FOUND !!!"
        log_msg = f"{sku} - {product_name}: No image URL found"
        log_skip(console_msg, log_msg)
        return False
    
    try:
        # Download image
        response = requests.get(product['image_url'], timeout=15)
        response.raise_for_status()
        
        # Get file extension
        ext = '.jpg'
        if 'png' in product['image_url'].lower():
            ext = '.png'
        
        # Create sanitized filename
        safe_name = sanitize_filename(product_name)
        filename = f"{sku} - {safe_name}{ext}"
        
        # Save temporarily to check background
        temp_path = os.path.join(category_folder, filename)
        
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        
        # Check for white background
        if not is_white_background(temp_path, product_name, sku):
            os.remove(temp_path)
            return False
        
        # Success - use tqdm.write to not disrupt progress bar
        tqdm.write(f"  ✓ {sku} - {safe_name}")
        return True
        
    except Exception as e:
        console_msg = f"!!! SKIP - DOWNLOAD ERROR !!! {e}"
        log_msg = f"{sku} - {product_name}: Download error - {e}"
        log_skip(console_msg, log_msg)
        return False


def main():
    """Main scraper workflow"""
    print("="*60)
    print("Product Image Scraper")
    print("="*60)
    
    # Delete existing log file for fresh start
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    # Delete existing output directory for fresh start
    if os.path.exists(OUTPUT_DIR):
        print(f"\nDeleting existing folder: {OUTPUT_DIR}/")
        shutil.rmtree(OUTPUT_DIR)
    
    # Load categories from JSON
    categories = load_categories()
    
    # Create output directory
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    
    # Create category folders
    for category_name in categories.keys():
        Path(os.path.join(OUTPUT_DIR, category_name)).mkdir(exist_ok=True)
    
    print(f"Created fresh folder structure in {OUTPUT_DIR}/\n")
    
    # Scrape all listing pages
    all_products = []
    print("\nScraping listing pages...")
    for page in tqdm(range(1, TOTAL_PAGES + 1), desc="Pages", unit="page"):
        products = scrape_listing_page(page)
        all_products.extend(products)
        time.sleep(REQUEST_DELAY)
    
    print(f"\n{'='*60}")
    print(f"Total products found: {len(all_products)}")
    print(f"{'='*60}\n")
    
    # Process each product
    successful = 0
    skipped = 0
    
    print(f"Processing {len(all_products)} products...")
    for product in tqdm(all_products, desc="Products", unit="product"):
        original_name = product['name']
        
        # Get SKU and image URL from product page
        product = scrape_product_details(product)
        if not product or not product.get('sku'):
            product_name = product.get('name', original_name) if product else original_name
            sku = product.get('sku', 'UNKNOWN') if product else 'UNKNOWN'
            console_msg = "!!! SKIP - NO SKU FOUND !!!"
            log_msg = f"{sku} - {product_name}: No SKU found"
            log_skip(console_msg, log_msg)
            skipped += 1
            continue
        
        # Determine category
        category = get_category(product['name'], categories)
        category_folder = os.path.join(OUTPUT_DIR, category)
        
        # Download and check image
        if download_image(product, category_folder):
            successful += 1
        else:
            skipped += 1
    
    # Summary
    total_processed = successful + skipped
    success_rate = (successful / total_processed * 100) if total_processed > 0 else 0
    
    summary = f"""
{'='*60}
SCRAPING COMPLETE
{'='*60}
Successfully downloaded: {successful} / {total_processed} ({success_rate:.1f}%)
Skipped (no white bg/errors): {skipped}
Images saved to: {OUTPUT_DIR}/
{'='*60}
"""
    print(summary)
    
    # Write summary to log file
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n{summary}")
    except Exception as e:
        print(f"Warning: Couldn't write summary to log: {e}")


if __name__ == "__main__":
    main()