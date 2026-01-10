"""
Product Image Scraper - Category-Based with Global Deduplication
Scrapes products from site's native category structure, detects duplicates globally,
and organizes into hierarchical folders matching the site's organization.
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
from datetime import datetime
from collections import defaultdict

# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "https://aquateak.com"
HOMEPAGE_URL = "https://aquateak.com/"

OUTPUT_DIR = "aquateak_products"
LOG_FILE = "scraper_log.txt"
CATEGORY_CONFIG = "category_prompts.json"

# White background detection
WHITE_THRESHOLD = 235
WHITE_PERCENTAGE = 0.85
SAMPLE_INTERVAL = 20

REQUEST_DELAY = 0.5

# ============================================================================
# Global Tracking
# ============================================================================

error_log = defaultdict(list)
downloaded_products = {}  # Key: sku, Value: category_path

# ============================================================================
# Helper Functions
# ============================================================================

def log_skip(error_category, sku, details):
    """Add error to categorized log."""
    error_log[error_category].append({
        'sku': sku,
        'details': details
    })


def write_log_file(total_products, successful, skipped, duplicates):
    """Write organized log file with all errors grouped by category."""
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("PRODUCT IMAGE SCRAPER - ERROR LOG\n")
            f.write("="*80 + "\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source: {HOMEPAGE_URL}\n")
            f.write("="*80 + "\n\n")
            
            for category, errors in sorted(error_log.items()):
                f.write(f"\n{'='*80}\n")
                f.write(f"{category.upper()} ({len(errors)} items)\n")
                f.write(f"{'='*80}\n\n")
                
                for error in errors:
                    f.write(f"SKU: {error['sku']}\n")
                    f.write(f"Details: {error['details']}\n")
                    f.write("-" * 80 + "\n")
            
            total_errors = sum(len(errors) for errors in error_log.values())
            total_attempted = successful + skipped
            success_rate = (successful / total_attempted * 100) if total_attempted > 0 else 0
            
            bg_dark_count = len(error_log.get("Background Too Dark", []))
            duplicate_count = len(error_log.get("Duplicate Product", []))
            other_errors = total_errors - bg_dark_count - duplicate_count
            
            f.write(f"\n{'='*80}\n")
            f.write(f"SUMMARY\n")
            f.write(f"{'='*80}\n\n")
            f.write(f"Total products found:          {total_products}\n")
            f.write(f"Unique products (deduplicated):{total_attempted}\n")
            f.write(f"Successfully downloaded:       {successful} ({success_rate:.1f}%)\n")
            f.write(f"Skipped (errors):              {skipped}\n")
            f.write(f"Duplicates detected:           {duplicates}\n\n")
            f.write(f"Error breakdown:\n")
            f.write(f"  Non-white background:        {bg_dark_count}\n")
            f.write(f"  Duplicate products:          {duplicate_count}\n")
            f.write(f"  Other errors:                {other_errors}\n\n")
            
            if error_log:
                f.write(f"Detailed error categories:\n")
                for category, errors in sorted(error_log.items()):
                    f.write(f"  {category}: {len(errors)}\n")
            
            f.write("\n" + "="*80 + "\n")
            
    except Exception as e:
        print(f"Warning: Couldn't write log file: {e}")


def sanitize_filename(name):
    """Sanitize filename by removing invalid characters."""
    name = name.replace('"', ' inch')
    for char in ['/', '\\', ':', '*', '?', '<', '>', '|']:
        name = name.replace(char, '-' if char in ['/', '\\'] else '')
    name = name.replace('™', '').replace('®', '')
    return re.sub(r'\s+', ' ', name).strip()


def sanitize_folder_name(name):
    """Sanitize folder name (similar to filename but keep ampersands as 'and')."""
    name = name.replace('&', 'and')
    name = name.replace('"', ' inch')
    for char in ['/', '\\', ':', '*', '?', '<', '>', '|']:
        name = name.replace(char, '')
    name = name.replace('™', '').replace('®', '')
    return re.sub(r'\s+', ' ', name).strip()


def is_white_background(image_path, sku):
    """Check if image has white background by sampling perimeter pixels."""
    try:
        img = Image.open(image_path).convert('RGB')
        width, height = img.size
        
        samples = []
        for x in range(0, width, SAMPLE_INTERVAL):
            samples.append(img.getpixel((x, 0)))
            samples.append(img.getpixel((x, height - 1)))
        for y in range(0, height, SAMPLE_INTERVAL):
            samples.append(img.getpixel((0, y)))
            samples.append(img.getpixel((width - 1, y)))
        
        white_count = sum(1 for r, g, b in samples 
                         if r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD)
        
        white_ratio = white_count / len(samples)
        is_white = white_ratio >= WHITE_PERCENTAGE
        
        if not is_white:
            log_skip("Background Too Dark", sku,
                    f"{white_ratio*100:.1f}% white pixels (needs {WHITE_PERCENTAGE*100:.1f}%)")
            tqdm.write(f"  ⚠ SKIP - Background too dark ({white_ratio*100:.1f}%)")
        
        return is_white
        
    except Exception as e:
        log_skip("Background Check Error", sku, str(e))
        tqdm.write(f"  ⚠ SKIP - Error checking background: {e}")
        return False


def extract_category_structure():
    """Extract full category hierarchy from homepage navigation."""
    try:
        response = requests.get(HOMEPAGE_URL, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        structure = {}
        
        nav = soup.find('nav')
        if not nav:
            nav = soup.find(attrs={'role': 'navigation'})
        
        if not nav:
            return {}
        
        top_level_items = nav.find_all('li', recursive=False) or nav.find('ul').find_all('li', recursive=False)
        
        for nav_item in top_level_items:
            links = nav_item.find_all('a', recursive=False)
            if not links:
                continue
            
            top_link = links[0]
            top_name = top_link.get_text(strip=True)
            
            # Only process Bathroom, Indoor, Outdoor
            if top_name not in ['Bathroom', 'Indoor', 'Outdoor']:
                continue
            
            structure[top_name] = {}
            dropdown_uls = nav_item.find_all('ul')
            
            if not dropdown_uls:
                continue
            
            for dropdown_ul in dropdown_uls:
                section_items = dropdown_ul.find_all('li', recursive=False)
                
                for section_item in section_items:
                    section_links = section_item.find_all('a')
                    if not section_links:
                        continue
                    
                    section_name = section_links[0].get_text(strip=True)
                    
                    if 'Collection' in section_name or 'Shop All' in section_name:
                        continue
                    
                    sub_ul = section_item.find('ul')
                    if not sub_ul:
                        continue
                    
                    structure[top_name][section_name] = {}
                    granular_items = sub_ul.find_all('li')
                    
                    for granular_item in granular_items:
                        granular_link = granular_item.find('a')
                        if not granular_link:
                            continue
                        
                        granular_name = granular_link.get_text(strip=True)
                        granular_url = granular_link.get('href', '')
                        
                        if 'Shop All' in granular_name:
                            continue
                        
                        if granular_url and not granular_url.startswith('http'):
                            granular_url = BASE_URL + granular_url
                        
                        if granular_url:
                            structure[top_name][section_name][granular_name] = granular_url
        
        return structure
        
    except Exception as e:
        print(f"Error extracting category structure: {e}")
        import traceback
        traceback.print_exc()
        return {}


def get_largest_image_url(soup):
    """Extract largest available product image URL."""
    img_tag = soup.select_one('.productView-image img')
    if img_tag:
        src = img_tag.get('src', '') or img_tag.get('data-src', '')
        if src:
            return re.sub(r'/\d+x\d+/', '/1280x1280/', src)
    
    zoom_img = soup.select_one('[data-zoom-image]')
    if zoom_img:
        return zoom_img.get('data-zoom-image', '')
    
    return None


def scrape_category_page(category_url, page=1):
    """Scrape single category page for product names and URLs."""
    try:
        url = f"{category_url}?page={page}" if page > 1 else category_url
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        products = []
        product_cards = soup.select('.product')
        
        for card in product_cards:
            name_tag = card.select_one('.card-title a')
            if not name_tag:
                continue
            
            product_name = name_tag.get_text(strip=True)
            product_url = name_tag['href']
            
            if not product_url.startswith('http'):
                product_url = BASE_URL + product_url
            
            products.append({'name': product_name, 'url': product_url})
        
        # Check for pagination
        has_next_page = soup.select_one('.pagination-item--next:not(.pagination-item--disabled)')
        
        return products, has_next_page is not None
        
    except Exception as e:
        print(f"Error scraping category page {category_url}: {e}")
        return [], False


def scrape_product_details(product):
    """Visit product page to get SKU and image URL."""
    time.sleep(REQUEST_DELAY)
    
    try:
        response = requests.get(product['url'], timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        sku_element = soup.find('dt', string='SKU:')
        if sku_element:
            sku_dd = sku_element.find_next_sibling('dd')
            if sku_dd:
                product['sku'] = sku_dd.get_text(strip=True)
        
        product['image_url'] = get_largest_image_url(soup)
        
        return product
        
    except Exception as e:
        log_skip("Page Fetch Error", "UNKNOWN", f"Failed to fetch: {e}")
        return None


def download_image(product, category_folder, category_path):
    """Download product image if not duplicate."""
    sku = product.get('sku', 'UNKNOWN')
    product_name = product['name']
    
    # Check for duplicate
    if sku in downloaded_products:
        log_skip("Duplicate Product", sku,
                f"Already downloaded in: {downloaded_products[sku]}")
        tqdm.write(f"  ⚠ SKIP - {sku} - Duplicate (found in {downloaded_products[sku]})")
        return False
    
    if not product.get('image_url'):
        log_skip("No Image URL", sku, "No image URL found")
        tqdm.write(f"  ⚠ SKIP - {sku} - No image URL")
        return False
    
    try:
        response = requests.get(product['image_url'], timeout=15)
        response.raise_for_status()
        
        # Detect original format and preserve it
        content_type = response.headers.get('content-type', '')
        if 'png' in content_type.lower() or product['image_url'].lower().endswith('.png'):
            ext = '.png'
        else:
            ext = '.jpg'
        
        safe_name = sanitize_filename(product_name)
        filename = f"{sku} - {safe_name}{ext}"
        temp_path = os.path.join(category_folder, filename)
        
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        
        if not is_white_background(temp_path, sku):
            os.remove(temp_path)
            return False
        
        downloaded_products[sku] = category_path
        
        tqdm.write(f"  ✓ {sku} - {safe_name}")
        return True
        
    except Exception as e:
        log_skip("Download Error", sku, str(e))
        tqdm.write(f"  ⚠ SKIP - {sku} - Download error: {e}")
        return False


def main():
    """Main scraper workflow."""
    print("="*60)
    print("Product Image Scraper - Category-Based")
    print("="*60)
    
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    error_log.clear()
    downloaded_products.clear()
    
    if os.path.exists(OUTPUT_DIR):
        print(f"\nDeleting existing folder: {OUTPUT_DIR}/")
        shutil.rmtree(OUTPUT_DIR)
    
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    
    # Extract category structure from site
    print("\nExtracting category structure from site...")
    structure = extract_category_structure()
    
    if not structure:
        print("✗ ERROR: Could not extract category structure")
        return
    
    total_categories = sum(len(list(granular.keys())) for top in structure.values() 
                          for mid in top.values() for granular in [mid] if isinstance(mid, dict))
    print(f"✓ Found {total_categories} granular categories\n")
    
    # Create folder structure
    for top_name, mid_level in structure.items():
        for mid_name, granular_level in mid_level.items():
            for granular_name in granular_level.keys():
                folder_path = os.path.join(
                    OUTPUT_DIR,
                    sanitize_folder_name(top_name),
                    sanitize_folder_name(mid_name),
                    sanitize_folder_name(granular_name)
                )
                Path(folder_path).mkdir(parents=True, exist_ok=True)
    
    print(f"Created folder structure in {OUTPUT_DIR}/\n")
    
    # Count total products first
    print("Counting total products...")
    total_products_to_scrape = 0
    for top_name, mid_level in structure.items():
        for mid_name, granular_level in mid_level.items():
            for granular_name, category_url in granular_level.items():
                page = 1
                while True:
                    products, has_next = scrape_category_page(category_url, page)
                    if not products:
                        break
                    total_products_to_scrape += len(products)
                    if not has_next:
                        break
                    page += 1
    
    print(f"✓ Found {total_products_to_scrape} total products to process\n")
    
    # Now scrape with single progress bar
    successful = 0
    skipped = 0
    
    with tqdm(total=total_products_to_scrape, desc="Processing products", unit="product") as pbar:
        for top_name, mid_level in structure.items():
            pbar.write(f"\n{'='*60}")
            pbar.write(f"Processing: {top_name}")
            pbar.write(f"{'='*60}")
            
            for mid_name, granular_level in mid_level.items():
                for granular_name, category_url in granular_level.items():
                    category_path = f"{top_name}/{mid_name}/{granular_name}"
                    folder_path = os.path.join(
                        OUTPUT_DIR,
                        sanitize_folder_name(top_name),
                        sanitize_folder_name(mid_name),
                        sanitize_folder_name(granular_name)
                    )
                    
                    # Scrape all pages for this category
                    page = 1
                    while True:
                        products, has_next = scrape_category_page(category_url, page)
                        
                        if not products:
                            break
                        
                        for product in products:
                            product = scrape_product_details(product)
                            
                            if not product or not product.get('sku'):
                                skipped += 1
                                pbar.update(1)
                                continue
                            
                            if download_image(product, folder_path, category_path):
                                successful += 1
                            else:
                                skipped += 1
                            
                            pbar.update(1)
                        
                        if not has_next:
                            break
                        
                        page += 1
                        time.sleep(REQUEST_DELAY)
    
    duplicates = len(error_log.get("Duplicate Product", []))
    
    write_log_file(total_products_to_scrape, successful, skipped, duplicates)
    
    success_rate = (successful / (successful + skipped) * 100) if (successful + skipped) > 0 else 0
    
    summary = f"""
{'='*60}
SCRAPING COMPLETE
{'='*60}
Total products found:          {total_products_to_scrape}
Unique products (deduplicated):{successful + skipped}
Successfully downloaded:       {successful} ({success_rate:.1f}%)
Skipped (errors):              {skipped}
Duplicates detected:           {duplicates}
Images saved to:               {OUTPUT_DIR}/
Error log:                     {LOG_FILE}
{'='*60}
"""
    print(summary)


if __name__ == "__main__":
    main()