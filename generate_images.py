"""
AI Image Generation Pipeline - BATCH API VERSION
50% cheaper! $0.12/image instead of $0.24/image for 4K

REQUIRES: pip install google-genai

Trade-off: Results in up to 24 hours (usually faster)
"""

import os
import json
import base64
import shutil
import time
from datetime import datetime
from PIL import Image
from io import BytesIO
from tqdm import tqdm

# Use official Google SDK for proper large file handling
from google import genai
from google.genai import types

# ============================================================================
# CONFIGURATION
# ============================================================================

TEST_MODE = False
GEMINI_MODEL = "gemini-3-pro-image-preview"

DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_IMAGE_SIZE = "4K"
JPEG_QUALITY = 95

VARIANTS_PRODUCTION = {
    'white': 1, 'white_in_use': 2, 'white_fitted': 1,
    'white_in_use_fitted': 2, 'room': 2, 'tight': 5, 'cropped': 3,
}
VARIANTS_TEST = {k: 1 for k in VARIANTS_PRODUCTION.keys()}

SUPPORTED_ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

INPUT_FOLDER = "aquateak_products"
OUTPUT_FOLDER = "generated_images"
FLAT_OUTPUT_FOLDER = "all_generated"
BATCH_FOLDER = "batch_jobs"
SHOT_PROMPTS_FILE = "shot_prompts.json"
CATEGORY_PROMPTS_FILE = "category_prompts.json"

os.makedirs(BATCH_FOLDER, exist_ok=True)

# ============================================================================
# API Setup
# ============================================================================

def load_api_key():
    try:
        with open('apikey.txt') as f:
            return f.read().strip()
    except:
        print("✗ apikey.txt not found!")
        return None

API_KEY = load_api_key()

# Initialize the official client
client = genai.Client(api_key=API_KEY) if API_KEY else None

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
    with open(SHOT_PROMPTS_FILE) as f:
        shot = json.load(f)
    with open(CATEGORY_PROMPTS_FILE) as f:
        cat = json.load(f)
    return shot, cat

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
                                    'src': img_path,
                                    'out_dir': out_dir,
                                    'out': out_path,
                                    'fname': fname,
                                    'prompt': get_prompt(shot_cfg, cat_cfg, top, mid, gran, internal, product, state),
                                    'ar': fitted_ar if fitted else DEFAULT_ASPECT_RATIO,
                                    'sku': sku,
                                })
    return tasks, skipped

# ============================================================================
# Batch API using Official SDK
# ============================================================================

def create_batch_request(task, request_id):
    """Create request object for batch."""
    img_b64 = image_to_base64(task['src'])
    
    return {
        "key": request_id,
        "request": {
            "model": f"models/{GEMINI_MODEL}",
            "contents": [{
                "parts": [
                    {"text": task['prompt']},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {
                    "aspectRatio": task['ar'],
                    "imageSize": DEFAULT_IMAGE_SIZE
                }
            }
        }
    }

def write_batch_jsonl(tasks, output_file):
    """Write all tasks to JSONL file."""
    print(f"\nCreating batch request file: {output_file}")
    
    with open(output_file, 'w') as f:
        for i, task in enumerate(tqdm(tasks, desc="Building JSONL")):
            request = create_batch_request(task, str(i))
            f.write(json.dumps(request) + '\n')
    
    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"✓ Created {output_file} ({size_mb:.1f} MB)")
    return output_file

def upload_file_resumable(filepath):
    """Upload large file using official SDK with resumable upload."""
    print(f"\nUploading {filepath} (this may take a few minutes for large files)...")
    
    try:
        # Official SDK handles resumable upload automatically
        uploaded_file = client.files.upload(
            file=filepath,
            config=types.UploadFileConfig(
                mime_type="application/jsonl",
                display_name=os.path.basename(filepath)
            )
        )
        
        print(f"✓ Uploaded: {uploaded_file.name}")
        print(f"  URI: {uploaded_file.uri}")
        return uploaded_file.name
        
    except Exception as e:
        print(f"✗ Upload failed: {e}")
        return None

def submit_batch_job(input_file_name):
    """Submit batch job."""
    print(f"\nSubmitting batch job...")
    
    try:
        batch_job = client.batches.create(
            model=GEMINI_MODEL,
            src=types.BatchJobSource(file_name=input_file_name),
            config=types.CreateBatchJobConfig(
                display_name=f"product-images-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
        )
        
        print(f"✓ Batch job created: {batch_job.name}")
        return batch_job.name
        
    except Exception as e:
        print(f"✗ Batch submit failed: {e}")
        return None

def poll_batch_status(batch_name):
    """Poll until complete with progress updates."""
    print(f"\nPolling batch status...")
    print("(Can take 1-24 hours. You can Ctrl+C and check later)")
    print(f"To check later: python generate_images_batch.py --check {batch_name}\n")
    
    while True:
        try:
            batch = client.batches.get(name=batch_name)
            
            state = batch.state.name if hasattr(batch.state, 'name') else str(batch.state)
            
            # Try to get progress counts
            succeeded = getattr(batch, 'succeeded_count', '?')
            failed = getattr(batch, 'failed_count', '?')
            total = getattr(batch, 'total_count', '?')
            
            print(f"  {datetime.now().strftime('%H:%M:%S')} | Status: {state} | Done: {succeeded}/{total} | Failed: {failed}")
            
            if 'SUCCEEDED' in state:
                print("\n✓ Batch job completed!")
                return batch
            elif 'FAILED' in state:
                print("\n✗ Batch job failed!")
                return None
            elif 'CANCELLED' in state:
                print("\n✗ Batch job cancelled")
                return None
            
            time.sleep(60)
            
        except Exception as e:
            print(f"  Status check error: {e}")
            time.sleep(60)

def download_results(batch, tasks):
    """Download generated images from completed batch."""
    print("\nDownloading results...")
    
    try:
        # Get the destination file
        dest_file = batch.dest.file_name if hasattr(batch, 'dest') else None
        
        if not dest_file:
            print("No output file in batch result")
            return 0, len(tasks)
        
        # Download the results file
        print(f"Downloading {dest_file}...")
        
        # Read results - the SDK should give us the content
        results_content = client.files.download(name=dest_file)
        
        success = 0
        failed = 0
        
        for line in results_content.strip().split('\n'):
            try:
                result = json.loads(line)
                key = result.get('key')
                
                if key is None:
                    continue
                
                task_idx = int(key)
                task = tasks[task_idx]
                
                if 'error' in result:
                    print(f"  ✗ {task['fname']}: {result['error']}")
                    failed += 1
                    continue
                
                # Extract image
                response = result.get('response', {})
                candidates = response.get('candidates', [])
                
                if not candidates:
                    failed += 1
                    continue
                
                parts = candidates[0].get('content', {}).get('parts', [])
                
                for part in parts:
                    if 'inlineData' in part:
                        img_data = part['inlineData'].get('data')
                        if img_data:
                            os.makedirs(task['out_dir'], exist_ok=True)
                            img = Image.open(BytesIO(base64.b64decode(img_data)))
                            img.save(task['out'], "JPEG", quality=JPEG_QUALITY)
                            success += 1
                            break
                else:
                    failed += 1
                    
            except Exception as e:
                print(f"  Error processing result: {e}")
                failed += 1
        
        return success, failed
        
    except Exception as e:
        print(f"Download failed: {e}")
        return 0, len(tasks)

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

def flatten():
    print("\nFlattening...")
    if os.path.exists(FLAT_OUTPUT_FOLDER): shutil.rmtree(FLAT_OUTPUT_FOLDER)
    os.makedirs(FLAT_OUTPUT_FOLDER)
    n = 0
    for root, _, files in os.walk(OUTPUT_FOLDER):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                shutil.copy2(os.path.join(root, f), os.path.join(FLAT_OUTPUT_FOLDER, f))
                n += 1
    print(f"✓ {n} images → {FLAT_OUTPUT_FOLDER}/")

# ============================================================================
# Chunked Batch Processing (for large jobs)
# ============================================================================

CHUNK_SIZE = 500  # Images per batch job (keeps file size manageable ~100MB)

def run_chunked_batches(tasks):
    """Split into multiple smaller batch jobs."""
    total_chunks = (len(tasks) + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"\nSplitting {len(tasks)} images into {total_chunks} batch jobs ({CHUNK_SIZE} each)")
    
    all_batch_names = []
    
    for chunk_idx in range(total_chunks):
        start = chunk_idx * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(tasks))
        chunk_tasks = tasks[start:end]
        
        print(f"\n{'='*40}")
        print(f"CHUNK {chunk_idx + 1}/{total_chunks} ({len(chunk_tasks)} images)")
        print(f"{'='*40}")
        
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        jsonl_file = os.path.join(BATCH_FOLDER, f"batch_chunk{chunk_idx}_{timestamp}.jsonl")
        
        # Create JSONL for this chunk
        write_batch_jsonl(chunk_tasks, jsonl_file)
        
        # Save task mapping for this chunk
        task_map_file = os.path.join(BATCH_FOLDER, f"task_map_chunk{chunk_idx}_{timestamp}.json")
        with open(task_map_file, 'w') as f:
            json.dump({
                'start_idx': start,
                'tasks': [{'out': t['out'], 'out_dir': t['out_dir'], 'fname': t['fname']} for t in chunk_tasks]
            }, f)
        
        # Upload
        file_name = upload_file_resumable(jsonl_file)
        if not file_name:
            print(f"✗ Chunk {chunk_idx + 1} upload failed, skipping")
            continue
        
        # Submit
        batch_name = submit_batch_job(file_name)
        if batch_name:
            all_batch_names.append({
                'batch_name': batch_name,
                'chunk_idx': chunk_idx,
                'task_map_file': task_map_file,
                'num_tasks': len(chunk_tasks)
            })
    
    # Save all batch info
    all_batches_file = os.path.join(BATCH_FOLDER, f"all_batches_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    with open(all_batches_file, 'w') as f:
        json.dump(all_batch_names, f, indent=2)
    
    print(f"\n✓ Submitted {len(all_batch_names)} batch jobs")
    print(f"✓ Saved batch info to {all_batches_file}")
    
    return all_batch_names, all_batches_file

def monitor_all_batches(batches_file):
    """Monitor multiple batch jobs until all complete."""
    with open(batches_file) as f:
        batches = json.load(f)
    
    print(f"\nMonitoring {len(batches)} batch jobs...")
    
    completed = []
    pending = list(batches)
    
    while pending:
        still_pending = []
        
        for batch_info in pending:
            try:
                batch = client.batches.get(name=batch_info['batch_name'])
                state = batch.state.name if hasattr(batch.state, 'name') else str(batch.state)
                
                if 'SUCCEEDED' in state:
                    print(f"  ✓ Chunk {batch_info['chunk_idx'] + 1} complete!")
                    completed.append((batch_info, batch))
                elif 'FAILED' in state or 'CANCELLED' in state:
                    print(f"  ✗ Chunk {batch_info['chunk_idx'] + 1} failed")
                else:
                    still_pending.append(batch_info)
                    
            except Exception as e:
                still_pending.append(batch_info)
        
        pending = still_pending
        
        if pending:
            print(f"  {datetime.now().strftime('%H:%M:%S')} | Completed: {len(completed)}/{len(batches)} | Pending: {len(pending)}")
            time.sleep(60)
    
    return completed

# ============================================================================
# Main
# ============================================================================

def main():
    import sys
    
    print("="*60)
    print("AI Image Generation - BATCH API (50% cheaper!)")
    print("="*60)
    print(f"\n4K pricing: $0.12/image (vs $0.24 standard)")
    print("Trade-off: Results in 1-24 hours\n")
    
    if not API_KEY or not client:
        print("✗ API key not found")
        return
    
    # Check for --monitor argument to resume monitoring
    if len(sys.argv) > 2 and sys.argv[1] == '--monitor':
        batches_file = sys.argv[2]
        print(f"Resuming monitoring from: {batches_file}")
        completed = monitor_all_batches(batches_file)
        print(f"\n✓ {len(completed)} batches completed")
        print("Run full script again to download results")
        return
    
    # Check for --check argument for single batch
    if len(sys.argv) > 2 and sys.argv[1] == '--check':
        batch_name = sys.argv[2]
        print(f"Checking status of: {batch_name}")
        batch = poll_batch_status(batch_name)
        return
    
    if not os.path.exists(INPUT_FOLDER):
        print(f"✗ {INPUT_FOLDER} not found")
        return
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    shot_cfg, cat_cfg = load_config()
    variants = VARIANTS_TEST if TEST_MODE else VARIANTS_PRODUCTION
    
    # Build tasks
    tasks, skipped = build_tasks(shot_cfg, cat_cfg, variants)
    print(f"✓ Already done: {skipped}")
    print(f"→ To generate: {len(tasks)}")
    
    if not tasks:
        print("\n✓ All images already complete!")
        flatten()
        return
    
    # Cost estimate
    cost_standard = len(tasks) * 0.24
    cost_batch = len(tasks) * 0.12
    savings = cost_standard - cost_batch
    print(f"\n💰 Cost estimate:")
    print(f"   Standard API: ${cost_standard:,.0f}")
    print(f"   Batch API:    ${cost_batch:,.0f}")
    print(f"   You save:     ${savings:,.0f} (50%!)")
    
    print(f"\nWill split into chunks of {CHUNK_SIZE} images each")
    input(f"\nPress Enter to start batch job for {len(tasks)} images...")
    
    # Copy originals
    print("\nCopying original images...")
    copy_originals(tasks)
    
    # Use chunked approach for large jobs
    batches, batches_file = run_chunked_batches(tasks)
    
    if not batches:
        print("No batches submitted successfully")
        return
    
    print(f"\n{'='*60}")
    print(f"ALL BATCHES SUBMITTED!")
    print(f"{'='*60}")
    print(f"Total batches: {len(batches)}")
    print(f"Batch info saved to: {batches_file}")
    print(f"\nNow waiting for completion (can take 1-24 hours)...")
    print(f"You can Ctrl+C and check later with:")
    print(f"  python generate_images_batch.py --monitor {batches_file}")
    
    # Monitor all batches
    completed = monitor_all_batches(batches_file)
    
    # Download all results
    success = 0
    failed = 0
    
    for batch_info, batch in completed:
        with open(batch_info['task_map_file']) as f:
            task_map = json.load(f)
        
        chunk_tasks = []
        for t in task_map['tasks']:
            chunk_tasks.append(t)
        
        s, f = download_results(batch, chunk_tasks)
        success += s
        failed += f
    
    print(f"\n{'='*60}")
    print("BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"✓ Generated: {success}")
    print(f"✗ Failed: {failed}")
    
    if failed > 0:
        print(f"\nTo retry failed: python generate_images.py")
    
    flatten()

if __name__ == "__main__":
    main()