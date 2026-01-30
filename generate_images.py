"""
AI Image Generation Pipeline
Supports both real-time API and batch API (50% cheaper) modes.
"""

import os
import json
import base64
import shutil
import time
import sys
from datetime import datetime
from PIL import Image
from io import BytesIO
from tqdm import tqdm
import requests

from google import genai
from google.genai import types

# ============================================================================
# FOLDER CONFIGURATION
# ============================================================================

INPUT_FOLDER = "inputs/aquateak_products"
OUTPUT_FOLDER = "outputs/generated_images"
BATCH_FOLDER = "outputs/batch_jobs"
LOG_FOLDER = "logs"
PROMPT_FOLDER = "prompts"

SHOT_PROMPTS_FILE = os.path.join(PROMPT_FOLDER, "shot_prompts.json")
CATEGORY_PROMPTS_FILE = os.path.join(PROMPT_FOLDER, "category_prompts.json")
API_KEY_FILE = "apikey.txt"
TEMP_BATCH_FILE = os.path.join(LOG_FOLDER, "temp_batch_download.jsonl")

# ============================================================================
# GENERATION SETTINGS
# ============================================================================

GEMINI_MODEL = "gemini-3-pro-image-preview"

DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_IMAGE_SIZE = "4K"
JPEG_QUALITY = 95

# Real-time API rate limiting (Tier 1 = 10 IPM)
MAX_PARALLEL_REQUESTS = 2
MIN_REQUEST_INTERVAL = 7.0
API_RETRY_MAX_ATTEMPTS = 5
API_RETRY_BASE_DELAY_SECONDS = 30

# Batch API settings
CHUNK_SIZE = 1000  # Images per batch job

VARIANTS_PRODUCTION = {
    'white': 1, 'white_in_use': 2, 'white_fitted': 1,
    'white_in_use_fitted': 2, 'room': 2, 'tight': 5, 'cropped': 3,
}
VARIANTS_TEST = {k: 1 for k in VARIANTS_PRODUCTION.keys()}

SUPPORTED_ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

# ============================================================================
# API Setup
# ============================================================================

def load_api_key():
    try:
        with open(API_KEY_FILE) as f:
            return f.read().strip()
    except:
        print("✗ apikey.txt not found!")
        return None

API_KEY = load_api_key()
client = genai.Client(api_key=API_KEY) if API_KEY else None

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ============================================================================
# Helpers
# ============================================================================

def find_best_ar(path):
    try:
        with Image.open(path) as img:
            r = img.size[0] / img.size[1]
    except:
        return "1:1"
    best, best_d = "1:1", 999
    for ar in SUPPORTED_ASPECT_RATIOS:
        w, h = map(int, ar.split(':'))
        d = abs(r - w/h)
        if d < best_d:
            best, best_d = ar, d
    return best

def load_config():
    try:
        with open(SHOT_PROMPTS_FILE) as f:
            shot = json.load(f)
        with open(CATEGORY_PROMPTS_FILE) as f:
            cat = json.load(f)
        return shot, cat
    except FileNotFoundError as e:
        print(f"✗ Config file not found: {e.filename}")
        print(f"  Expected: {SHOT_PROMPTS_FILE} and {CATEGORY_PROMPTS_FILE}")
        return None, None

def file_ok(path):
    return os.path.exists(path) and os.path.getsize(path) > 1000

def image_to_base64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

def get_prompt(shot_cfg, cat_cfg, top, mid, gran, shot_type, product, state=None):
    base = shot_cfg.get("base_prompts", {}).get(shot_type, "")
    p = f"Product: {product}. {base}"
    if shot_type not in ['white', 'white-in-use', 'white-fitted', 'white-in-use-fitted']:
        try:
            p = f"{p} Setting: {cat_cfg['categories'][top][mid][gran]['prompt']}"
        except KeyError:
            pass
    if state:
        mod = shot_cfg.get("state_modifiers", {}).get(state, "")
        if mod:
            p = f"{p} STATE: {mod}"
    return p

# ============================================================================
# Task Building
# ============================================================================

def build_tasks(shot_cfg, cat_cfg, variants):
    tasks, skipped = [], 0
    shots = [
        ('white', 'White refresh', '1', False),
        ('white-fitted', 'White fitted', '1A', True),
        ('white-in-use', 'White in use', '2', False),
        ('white-in-use-fitted', 'White in use fitted', '2A', True),
        ('room', 'Full room', '3', False),
        ('tight', 'Tight', '4', False),
        ('cropped', 'Cropped', '5', False),
    ]
    for top in os.listdir(INPUT_FOLDER):
        tp = os.path.join(INPUT_FOLDER, top)
        if not os.path.isdir(tp): continue
        for mid in os.listdir(tp):
            mp = os.path.join(tp, mid)
            if not os.path.isdir(mp): continue
            for gran in os.listdir(mp):
                gp = os.path.join(mp, gran)
                if not os.path.isdir(gp): continue
                try:
                    openable = cat_cfg["categories"][top][mid][gran].get("openable", False)
                except:
                    openable = False
                files = [f for f in os.listdir(gp) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                if TEST_MODE: files = files[:1]
                for img_file in files:
                    img_path = os.path.join(gp, img_file)
                    fitted_ar = find_best_ar(img_path)
                    sku = img_file.split(' - ')[0] if ' - ' in img_file else os.path.splitext(img_file)[0]
                    product = os.path.splitext(' - '.join(img_file.split(' - ')[1:]))[0] if ' - ' in img_file else sku
                    out_dir = os.path.join(OUTPUT_FOLDER, top, mid, gran, sku)
                    states = ['closed', 'open'] if openable else [None]
                    for state in states:
                        for internal, display, num, fitted in shots:
                            cnt = variants.get(internal.replace('-', '_'), 0)
                            for v in range(1, cnt + 1):
                                fname = f"{sku} - {num} {display}{' ' + state if state else ''} v{v}.jpg"
                                out_path = os.path.join(out_dir, fname)
                                if file_ok(out_path):
                                    skipped += 1
                                    continue
                                tasks.append({
                                    'src': img_path, 'out_dir': out_dir, 'out': out_path, 'fname': fname,
                                    'prompt': get_prompt(shot_cfg, cat_cfg, top, mid, gran, internal, product, state),
                                    'ar': fitted_ar if fitted else DEFAULT_ASPECT_RATIO, 'sku': sku,
                                })
    return tasks, skipped

def copy_originals(tasks):
    seen = set()
    for t in tasks:
        if t['src'] in seen: continue
        seen.add(t['src'])
        fname = os.path.basename(t['src'])
        sku = fname.split(' - ')[0] if ' - ' in fname else os.path.splitext(fname)[0]
        dest = os.path.join(t['out_dir'], f"{sku} - 0 Original{os.path.splitext(fname)[1]}")
        if not file_ok(dest):
            os.makedirs(t['out_dir'], exist_ok=True)
            try: shutil.copy2(t['src'], dest)
            except: pass

# ============================================================================
# Real-Time API Mode
# NOTE: Real-time implementation - verify API syntax matches your SDK version
# ============================================================================

def generate_single_image(task):
    """Generate single image via real-time API with retry logic."""
    img_b64 = image_to_base64(task['src'])
    for attempt in range(API_RETRY_MAX_ATTEMPTS):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[{"parts": [
                    {"text": task['prompt']},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]}],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=task['ar'], 
                        image_size=DEFAULT_IMAGE_SIZE
                    )
                )
            )
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    os.makedirs(task['out_dir'], exist_ok=True)
                    img = Image.open(BytesIO(base64.b64decode(part.inline_data.data)))
                    img.save(task['out'], "JPEG", quality=JPEG_QUALITY)
                    return True
            return False
        except Exception as e:
            if '429' in str(e) or '503' in str(e):
                delay = API_RETRY_BASE_DELAY_SECONDS * (attempt + 1)
                log(f"Rate limited, waiting {delay}s...")
                time.sleep(delay)
            else:
                log(f"Error: {e}")
                return False
    return False

def run_realtime_mode(tasks):
    """Run generation using real-time API."""
    log(f"Starting real-time generation of {len(tasks)} images")
    log(f"Rate: ~{60/MIN_REQUEST_INTERVAL:.0f} images/min")
    success, failed = 0, 0
    for task in tqdm(tasks, desc="Generating"):
        if generate_single_image(task):
            success += 1
        else:
            failed += 1
        time.sleep(MIN_REQUEST_INTERVAL)
    return success, failed

# ============================================================================
# Batch API Mode
# ============================================================================

def create_batch_request(task, request_id):
    img_b64 = image_to_base64(task['src'])
    return {
        "key": request_id,
        "request": {
            "model": f"models/{GEMINI_MODEL}",
            "contents": [{"parts": [
                {"text": task['prompt']},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
            ]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": task['ar'], "imageSize": DEFAULT_IMAGE_SIZE}
            }
        }
    }

def write_batch_jsonl(tasks, output_file):
    log(f"Creating batch file: {output_file}")
    with open(output_file, 'w') as f:
        for i, task in enumerate(tqdm(tasks, desc="Building JSONL")):
            f.write(json.dumps(create_batch_request(task, str(i))) + '\n')
    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    log(f"✓ Created {output_file} ({size_mb:.1f} MB)")

def upload_file_resumable(filepath):
    log(f"Uploading {filepath}...")
    try:
        uploaded = client.files.upload(
            file=filepath,
            config=types.UploadFileConfig(mime_type="application/jsonl", display_name=os.path.basename(filepath))
        )
        log(f"✓ Uploaded: {uploaded.name}")
        return uploaded.name
    except Exception as e:
        log(f"✗ Upload failed: {e}")
        return None

def submit_batch_job(input_file_name):
    log("Submitting batch job...")
    try:
        batch = client.batches.create(
            model=GEMINI_MODEL,
            src=types.BatchJobSource(file_name=input_file_name),
            config=types.CreateBatchJobConfig(display_name=f"images-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        )
        log(f"✓ Batch created: {batch.name}")
        return batch.name
    except Exception as e:
        log(f"✗ Submit failed: {e}")
        return None

def download_batch_to_file(file_name, output_path):
    """Stream download to disk to avoid RAM issues."""
    url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}:download?alt=media&key={API_KEY}"
    log(f"Downloading to {output_path}...")
    resp = requests.get(url, timeout=1800, stream=True)
    resp.raise_for_status()
    total = int(resp.headers.get('content-length', 0))
    downloaded, last_print = 0, 0
    with open(output_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                mb = downloaded / (1024 * 1024)
                if mb - last_print >= 50:
                    log(f"  {mb:.0f} / {total/(1024*1024):.0f} MB" if total else f"  {mb:.0f} MB")
                    last_print = mb
    log(f"Download complete: {downloaded/(1024*1024):.0f} MB")

def process_batch_results(results_path, tasks):
    """Process results file line by line."""
    success, failed = 0, 0
    log(f"Processing results...")
    with open(results_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                result = json.loads(line.strip())
                key = result.get('key')
                if key is None: continue
                task_idx = int(key)
                if task_idx >= len(tasks): continue
                task = tasks[task_idx]
                if 'error' in result:
                    failed += 1
                    continue
                candidates = result.get('response', {}).get('candidates', [])
                if not candidates:
                    failed += 1
                    continue
                parts = candidates[0].get('content', {}).get('parts', [])
                saved = False
                for part in parts:
                    if 'inlineData' in part:
                        img_data = part['inlineData'].get('data')
                        if img_data:
                            os.makedirs(task['out_dir'], exist_ok=True)
                            img = Image.open(BytesIO(base64.b64decode(img_data)))
                            img.save(task['out'], "JPEG", quality=JPEG_QUALITY)
                            success += 1
                            saved = True
                            if success % 50 == 0:
                                log(f"  Saved {success} images...")
                            break
                if not saved:
                    failed += 1
            except:
                failed += 1
    return success, failed

def run_batch_mode(tasks):
    """Run generation using batch API with chunking."""
    os.makedirs(BATCH_FOLDER, exist_ok=True)
    total_chunks = (len(tasks) + CHUNK_SIZE - 1) // CHUNK_SIZE
    log(f"Splitting {len(tasks)} images into {total_chunks} batches ({CHUNK_SIZE} each)")
    
    all_batches = []
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    
    # Submit all chunks
    for chunk_idx in range(total_chunks):
        start = chunk_idx * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(tasks))
        chunk_tasks = tasks[start:end]
        log(f"\n--- CHUNK {chunk_idx + 1}/{total_chunks} ({len(chunk_tasks)} images) ---")
        
        jsonl_file = os.path.join(BATCH_FOLDER, f"chunk{chunk_idx}_{timestamp}.jsonl")
        task_map_file = os.path.join(BATCH_FOLDER, f"taskmap{chunk_idx}_{timestamp}.json")
        
        write_batch_jsonl(chunk_tasks, jsonl_file)
        with open(task_map_file, 'w') as f:
            json.dump({'tasks': [{'out': t['out'], 'out_dir': t['out_dir']} for t in chunk_tasks]}, f)
        
        file_name = upload_file_resumable(jsonl_file)
        if not file_name: continue
        
        batch_name = submit_batch_job(file_name)
        if batch_name:
            all_batches.append({'batch_name': batch_name, 'chunk_idx': chunk_idx, 'task_map_file': task_map_file})
    
    batches_file = os.path.join(BATCH_FOLDER, f"all_batches_{timestamp}.json")
    with open(batches_file, 'w') as f:
        json.dump(all_batches, f, indent=2)
    log(f"\n✓ Submitted {len(all_batches)} batches. Info saved to {batches_file}")
    
    # Poll and download
    log("\nWaiting for completion (1-24 hours typical)...")
    log("Press Ctrl+C to exit - run with --resume to continue later\n")
    
    total_success, total_failed = 0, 0
    pending = list(all_batches)
    
    while pending:
        still_pending = []
        for batch_info in pending:
            try:
                batch = client.batches.get(name=batch_info['batch_name'])
                state = str(batch.state)
                if 'SUCCEEDED' in state:
                    log(f"✓ Chunk {batch_info['chunk_idx'] + 1} complete - downloading...")
                    with open(batch_info['task_map_file']) as f:
                        task_map = json.load(f)
                    download_batch_to_file(batch.dest.file_name, TEMP_BATCH_FILE)
                    s, f = process_batch_results(TEMP_BATCH_FILE, task_map['tasks'])
                    total_success += s
                    total_failed += f
                    log(f"Chunk {batch_info['chunk_idx'] + 1}: ✓ {s} | ✗ {f}")
                    if os.path.exists(TEMP_BATCH_FILE):
                        os.remove(TEMP_BATCH_FILE)
                elif 'FAILED' in state or 'CANCELLED' in state:
                    log(f"✗ Chunk {batch_info['chunk_idx'] + 1} failed")
                else:
                    still_pending.append(batch_info)
            except Exception as e:
                still_pending.append(batch_info)
        pending = still_pending
        if pending:
            log(f"Pending: {len(pending)}/{len(all_batches)} batches...")
            time.sleep(60)
    
    return total_success, total_failed

def resume_batches(batches_file):
    """Resume monitoring and downloading from existing batches file."""
    os.makedirs(LOG_FOLDER, exist_ok=True)
    log(f"Resuming from {batches_file}")
    with open(batches_file) as f:
        all_batches = json.load(f)
    
    total_success, total_failed = 0, 0
    pending = list(all_batches)
    
    while pending:
        still_pending = []
        for batch_info in pending:
            try:
                batch = client.batches.get(name=batch_info['batch_name'])
                state = str(batch.state)
                if 'SUCCEEDED' in state:
                    log(f"✓ Chunk {batch_info['chunk_idx'] + 1} complete - downloading...")
                    with open(batch_info['task_map_file']) as f:
                        task_map = json.load(f)
                    download_batch_to_file(batch.dest.file_name, TEMP_BATCH_FILE)
                    s, f = process_batch_results(TEMP_BATCH_FILE, task_map['tasks'])
                    total_success += s
                    total_failed += f
                    log(f"Chunk {batch_info['chunk_idx'] + 1}: ✓ {s} | ✗ {f}")
                    if os.path.exists(TEMP_BATCH_FILE):
                        os.remove(TEMP_BATCH_FILE)
                elif 'FAILED' in state or 'CANCELLED' in state:
                    log(f"✗ Chunk {batch_info['chunk_idx'] + 1} failed")
                else:
                    still_pending.append(batch_info)
            except Exception as e:
                still_pending.append(batch_info)
        pending = still_pending
        if pending:
            log(f"Pending: {len(pending)}/{len(all_batches)} batches...")
            time.sleep(60)
    
    log(f"\n{'='*60}")
    log(f"RESUME COMPLETE: ✓ {total_success} | ✗ {total_failed}")
    return total_success, total_failed

# ============================================================================
# Main
# ============================================================================

def main():
    print("="*60)
    print("AI Image Generation Pipeline")
    print("="*60)
    
    # Handle resume command
    if len(sys.argv) > 2 and sys.argv[1] == '--resume':
        resume_batches(sys.argv[2])
        return
    
    if not API_KEY or not client:
        print("✗ API key not found")
        return
    
    if not os.path.exists(INPUT_FOLDER):
        print(f"✗ {INPUT_FOLDER} not found")
        return
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(LOG_FOLDER, exist_ok=True)
    
    shot_cfg, cat_cfg = load_config()
    if not shot_cfg or not cat_cfg:
        return
    
    # Test mode selection
    print("\n" + "="*60)
    print("TEST MODE?")
    print("  y = 1 variant per shot type (fast, cheap, for testing)")
    print("  n = full production variants")
    print("="*60)
    test_choice = input("\nTest mode? (y/n): ").strip().lower()
    use_test_mode = test_choice in ['y', 'yes']
    
    if use_test_mode:
        print("→ Using TEST mode (1 variant each)")
    else:
        print("→ Using PRODUCTION mode (full variants)")
    
    variants = VARIANTS_TEST if use_test_mode else VARIANTS_PRODUCTION
    
    tasks, skipped = build_tasks(shot_cfg, cat_cfg, variants)
    print(f"\n✓ Already done: {skipped}")
    print(f"→ To generate: {len(tasks)}")
    
    if not tasks:
        print("\n✓ All images complete!")
        return
    
    # API mode selection
    print("\n" + "="*60)
    print("SELECT API MODE:")
    print("  [1] Real-time API  - $0.24/image, immediate results")
    print("  [2] Batch API      - $0.12/image, 1-24 hour wait (50% savings)")
    print("="*60)
    print("⚠️  Check your Google API tier rate limits before proceeding!")
    print("   Tier 1 (default): 10 images/min")
    print("   Tier 2: 50/min | Tier 3: 100/min")
    print("   https://ai.google.dev/pricing")
    print("="*60)
    
    choice = input("\nEnter 1 or 2: ").strip()
    
    cost_rt = len(tasks) * 0.24
    cost_batch = len(tasks) * 0.12
    
    if choice == '2':
        print(f"\n💰 Batch mode: ${cost_batch:,.0f} (saving ${cost_rt - cost_batch:,.0f})")
        input(f"Press Enter to submit {len(tasks)} images as batch jobs...")
        copy_originals(tasks)
        success, failed = run_batch_mode(tasks)
    else:
        est_minutes = len(tasks) * MIN_REQUEST_INTERVAL / 60
        print(f"\n💰 Real-time: ${cost_rt:,.0f}")
        print(f"⏱  Estimated: {est_minutes:.0f} min ({est_minutes/60:.1f} hours)")
        input(f"Press Enter to start generating {len(tasks)} images...")
        copy_originals(tasks)
        success, failed = run_realtime_mode(tasks)
    
    print(f"\n{'='*60}")
    print(f"COMPLETE: ✓ {success} generated | ✗ {failed} failed")
    print(f"Output: {OUTPUT_FOLDER}/")
    print("="*60)

if __name__ == "__main__":
    main()