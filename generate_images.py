"""
AI Image Generation Pipeline v3 (2026-05) - BATCH-ONLY, RESILIENT
- Model: Nano Banana Pro (gemini-3-pro-image-preview)
- Filename convention: "[SKU] Product Name.jpg"
- Output: outputs/generated_images/[SKU]/[SKU] - N Shot vK.jpg
- Crash-safe: state.json tracks every batch, just re-run script to resume
- Verbose error logs to logs/errors.log, concise stdout progress
"""

import os
import re
import json
import base64
import shutil
import time
import sys
import traceback
import logging
from datetime import datetime, timezone
from PIL import Image
from io import BytesIO
from tqdm import tqdm
import requests

from google import genai
from google.genai import types

# ============================================================================
# CONFIG
# ============================================================================

INPUT_FOLDER = "inputs/run2"
OUTPUT_FOLDER = "outputs/generated_images"
BATCH_FOLDER = "outputs/batch_jobs"
LOG_FOLDER = "logs"
PROMPT_FOLDER = "prompts"

SHOT_PROMPTS_FILE = os.path.join(PROMPT_FOLDER, "shot_prompts.json")
CATEGORY_PROMPTS_FILE = os.path.join(PROMPT_FOLDER, "category_prompts.json")
API_KEY_FILE = "apikey.txt"
STATE_FILE = os.path.join(BATCH_FOLDER, "state.json")
ERROR_LOG = os.path.join(LOG_FOLDER, "errors.log")

# Nano Banana Pro - strongest model
GEMINI_MODEL = "gemini-3-pro-image-preview"

# ============================================================================
# Google API Pricing (Nano Banana Pro, batch tier = 50% off real-time)
# Source: https://ai.google.dev/gemini-api/docs/pricing
# Update these if Google changes rates.
# ============================================================================

# $/M tokens (batch tier, already discounted 50% from real-time)
TEXT_INPUT_RATE_PER_M  = 1.00     # text prompt tokens
IMAGE_INPUT_RATE_PER_M = 0.55     # per uploaded input image tokens
IMAGE_OUTPUT_RATE_PER_M = 60.00   # per generated output image tokens

# Tokens per input image (fixed by Google)
TOKENS_PER_INPUT_IMAGE = 560

# Tokens per output image - varies by resolution (1:1 reference; other ARs ~same)
OUTPUT_TOKENS_BY_SIZE = {
    "512": 747,
    "1K":  1120,
    "2K":  1568,
    "4K":  2000,
}

# Real-time multiplier (for showing what user is saving)
REALTIME_MULTIPLIER = 2.0

DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_IMAGE_SIZE = "4K"
JPEG_QUALITY = 95

# Tier 1 batch enqueued-token cap is 2M for Pro Image. ~1k tokens/req input,
# so 500/chunk is a healthy safety margin.
CHUNK_SIZE = 500
# Tier 1 allows 100 concurrent batch jobs. Pause briefly between submissions.
INTER_SUBMIT_DELAY = 2.0
# Retry config for upload/submit/download
UPLOAD_MAX_RETRIES = 5
UPLOAD_RETRY_DELAY = 30   # seconds, multiplied by attempt
# Polling cadence
POLL_INTERVAL = 60        # seconds between status checks
POLL_HEARTBEAT = True     # print heartbeat every poll cycle even when nothing changes

VARIANTS_PRODUCTION = {
    'white': 1, 'white_in_use': 2, 'white_fitted': 1,
    'white_in_use_fitted': 2, 'room': 2, 'tight': 3, 'cropped': 3,
}

SUPPORTED_ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

# ============================================================================
# Logging setup
# ============================================================================

os.makedirs(LOG_FOLDER, exist_ok=True)
os.makedirs(BATCH_FOLDER, exist_ok=True)

err_logger = logging.getLogger('errors')
err_logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(ERROR_LOG)
fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
err_logger.addHandler(fh)

def info(msg):
    """Concise stdout-only print."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def warn(msg, exc=None):
    """Warning - print + file log with stack trace if exception."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] WARN {msg}", flush=True)
    if exc:
        err_logger.warning(f"{msg}\n{traceback.format_exc()}")
    else:
        err_logger.warning(msg)

def err(msg, exc=None):
    """Error - print + file log with full context."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR {msg}", flush=True)
    if exc:
        err_logger.error(f"{msg}\n{traceback.format_exc()}")
    else:
        err_logger.error(msg)

# ============================================================================
# API setup
# ============================================================================

def load_api_key():
    try:
        with open(API_KEY_FILE) as f:
            return f.read().strip()
    except Exception as e:
        err(f"could not read {API_KEY_FILE}", e)
        return None

API_KEY = load_api_key()
client = genai.Client(api_key=API_KEY) if API_KEY else None

def verify_api_key():
    """Free verification via models.list. No tokens charged."""
    if not client:
        return False, "no client"
    try:
        models = list(client.models.list())
        if not models:
            return False, "key works but no models returned"
        ids = [m.name for m in models if hasattr(m, 'name')]
        ok = any(GEMINI_MODEL in s for s in ids)
        msg = f"key valid, {len(models)} models visible"
        if not ok:
            msg += f" (warning: {GEMINI_MODEL} not enumerated - may still work)"
        return True, msg
    except Exception as e:
        err("api key verification failed", e)
        return False, f"verification failed: {e}"

# ============================================================================
# Filename / helpers
# ============================================================================

FILENAME_RE = re.compile(r'^\[([^\]]+)\]\s*(.+)$')

def parse_filename(filename):
    stem = os.path.splitext(filename)[0]
    m = FILENAME_RE.match(stem)
    if not m:
        return None, None
    sku_inner = m.group(1).strip()
    product = m.group(2).strip()
    return f"[{sku_inner}]", product

def find_best_ar(path):
    try:
        with Image.open(path) as img:
            r = img.size[0] / img.size[1]
    except Exception as e:
        warn(f"could not read image dimensions {path}", e)
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
        err(f"config file missing: {e.filename}")
        return None, None
    except json.JSONDecodeError as e:
        err(f"config file invalid JSON: {e}", e)
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
# State management (crash-safe resume)
# ============================================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception as e:
        warn(f"state file corrupted: {e}", e)
        return None

def estimate_text_tokens(text):
    """Rough estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)

def calculate_costs(tasks):
    """Compute cost estimate from REAL task data + Google's published rates.
    Nothing hardcoded per-image - everything derived.
    Returns dict with full breakdown.
    """
    n = len(tasks)
    if n == 0:
        return None

    # Real prompt tokens from actual task prompts
    total_prompt_tokens = sum(estimate_text_tokens(t['prompt']) for t in tasks)
    avg_prompt_tokens = total_prompt_tokens // n

    # Image tokens (fixed by Google)
    output_tokens_each = OUTPUT_TOKENS_BY_SIZE.get(DEFAULT_IMAGE_SIZE, 2000)
    total_input_img_tokens = n * TOKENS_PER_INPUT_IMAGE
    total_output_img_tokens = n * output_tokens_each

    # Derive cost from rates
    text_cost   = total_prompt_tokens     * TEXT_INPUT_RATE_PER_M  / 1_000_000
    img_in_cost = total_input_img_tokens  * IMAGE_INPUT_RATE_PER_M / 1_000_000
    img_out_cost= total_output_img_tokens * IMAGE_OUTPUT_RATE_PER_M / 1_000_000
    total_batch = text_cost + img_in_cost + img_out_cost
    total_realtime = total_batch * REALTIME_MULTIPLIER

    # Per-image derived (not hardcoded)
    per_img_batch = total_batch / n

    return {
        'n': n,
        'avg_prompt_tokens': avg_prompt_tokens,
        'total_prompt_tokens': total_prompt_tokens,
        'output_tokens_each': output_tokens_each,
        'text_cost': text_cost,
        'img_in_cost': img_in_cost,
        'img_out_cost': img_out_cost,
        'total_batch': total_batch,
        'total_realtime': total_realtime,
        'per_img_batch': per_img_batch,
    }

def save_state(state):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        err("could not save state file", e)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def elapsed_since(iso_str):
    try:
        t = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        delta = now - t
        s = int(delta.total_seconds())
        if s < 60: return f"{s}s"
        if s < 3600: return f"{s//60}m {s%60}s"
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h {m}m"
    except:
        return "?"

# ============================================================================
# Task building
# ============================================================================

def build_tasks(shot_cfg, cat_cfg, variants):
    tasks, skipped, parse_failed = [], 0, []
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
                except KeyError:
                    openable = False
                files = [f for f in os.listdir(gp) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                for img_file in files:
                    img_path = os.path.join(gp, img_file)
                    sku, product = parse_filename(img_file)
                    if not sku:
                        parse_failed.append(img_file)
                        continue
                    fitted_ar = find_best_ar(img_path)
                    out_dir = os.path.join(OUTPUT_FOLDER, sku)
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
    if parse_failed:
        warn(f"{len(parse_failed)} files did NOT match [SKU] format and were SKIPPED:")
        for f in parse_failed[:10]:
            err_logger.warning(f"  unparseable filename: {f}")
        if len(parse_failed) > 10:
            err_logger.warning(f"  ... and {len(parse_failed)-10} more (see logs/errors.log)")
    return tasks, skipped

def copy_originals(tasks):
    seen = set()
    copied = 0
    for t in tasks:
        if t['src'] in seen: continue
        seen.add(t['src'])
        fname = os.path.basename(t['src'])
        sku = t['sku']
        ext = os.path.splitext(fname)[1]
        dest = os.path.join(t['out_dir'], f"{sku} - 0 Original{ext}")
        if not file_ok(dest):
            os.makedirs(t['out_dir'], exist_ok=True)
            try:
                shutil.copy2(t['src'], dest)
                copied += 1
            except Exception as e:
                err(f"could not copy original {t['src']} -> {dest}", e)
    if copied:
        info(f"copied {copied} original images into output sku folders")

# ============================================================================
# Batch operations - resilient with retries
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
    info(f"building JSONL for {len(tasks)} tasks...")
    try:
        with open(output_file, 'w') as f:
            for i, task in enumerate(tasks):
                f.write(json.dumps(create_batch_request(task, str(i))) + '\n')
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        info(f"  ok {output_file} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        err(f"could not write batch JSONL {output_file}", e)
        return False

def upload_with_retry(filepath):
    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        try:
            uploaded = client.files.upload(
                file=filepath,
                config=types.UploadFileConfig(
                    mime_type="application/jsonl",
                    display_name=os.path.basename(filepath)
                )
            )
            info(f"  ok uploaded: {uploaded.name}")
            return uploaded.name
        except Exception as e:
            delay = UPLOAD_RETRY_DELAY * attempt
            warn(f"upload attempt {attempt}/{UPLOAD_MAX_RETRIES} failed for {filepath}: {e}", e)
            if attempt < UPLOAD_MAX_RETRIES:
                info(f"  retrying in {delay}s...")
                time.sleep(delay)
    err(f"upload permanently failed for {filepath} after {UPLOAD_MAX_RETRIES} attempts")
    return None

def submit_with_retry(input_file_name, chunk_idx):
    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        try:
            batch = client.batches.create(
                model=GEMINI_MODEL,
                src=types.BatchJobSource(file_name=input_file_name),
                config=types.CreateBatchJobConfig(
                    display_name=f"chunk{chunk_idx}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                )
            )
            info(f"  ok submitted batch: {batch.name}")
            return batch.name
        except Exception as e:
            delay = UPLOAD_RETRY_DELAY * attempt
            warn(f"submit attempt {attempt}/{UPLOAD_MAX_RETRIES} failed: {e}", e)
            if attempt < UPLOAD_MAX_RETRIES:
                info(f"  retrying in {delay}s...")
                time.sleep(delay)
    err(f"submit permanently failed for chunk {chunk_idx}")
    return None

def download_with_retry(file_name, output_path):
    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}:download?alt=media&key={API_KEY}"
            info(f"  downloading results -> {output_path}")
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
                        if mb - last_print >= 100:
                            if total:
                                info(f"    {mb:.0f} / {total/(1024*1024):.0f} MB")
                            else:
                                info(f"    {mb:.0f} MB")
                            last_print = mb
            info(f"  ok download complete: {downloaded/(1024*1024):.0f} MB")
            return True
        except Exception as e:
            delay = UPLOAD_RETRY_DELAY * attempt
            warn(f"download attempt {attempt}/{UPLOAD_MAX_RETRIES} failed: {e}", e)
            if attempt < UPLOAD_MAX_RETRIES:
                info(f"  retrying in {delay}s...")
                time.sleep(delay)
    err(f"download permanently failed for {file_name}")
    return False

def process_batch_results(results_path, task_map):
    success, failed = 0, 0
    failed_details = []
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    result = json.loads(line.strip())
                    key = result.get('key')
                    if key is None:
                        failed += 1
                        err_logger.warning(f"result missing key field: {line[:200]}")
                        continue
                    task_idx = int(key)
                    if task_idx >= len(task_map):
                        failed += 1
                        err_logger.warning(f"result key {task_idx} out of range")
                        continue
                    task = task_map[task_idx]
                    if 'error' in result:
                        failed += 1
                        err_logger.error(f"api returned error for task {task_idx} ({task.get('out')}): {result['error']}")
                        failed_details.append(task.get('out', '?'))
                        continue
                    candidates = result.get('response', {}).get('candidates', [])
                    if not candidates:
                        failed += 1
                        err_logger.error(f"no candidates for task {task_idx} ({task.get('out')}): {json.dumps(result)[:500]}")
                        failed_details.append(task.get('out', '?'))
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
                                break
                    if not saved:
                        failed += 1
                        err_logger.error(f"no image part for task {task_idx} ({task.get('out')})")
                        failed_details.append(task.get('out', '?'))
                except Exception as e:
                    failed += 1
                    err_logger.error(f"could not process result line: {line[:200]}\n{traceback.format_exc()}")
    except Exception as e:
        err(f"could not read results file {results_path}", e)
    return success, failed, failed_details

# ============================================================================
# Submission - incremental state save
# ============================================================================

def submit_all_chunks(tasks, state):
    """Submit chunks one at a time, saving state after each.
    Skips chunks already submitted in state file (resume safety)."""
    total_chunks = (len(tasks) + CHUNK_SIZE - 1) // CHUNK_SIZE
    info(f"splitting {len(tasks)} tasks into {total_chunks} chunks of {CHUNK_SIZE}")

    already_submitted = {b['chunk_idx'] for b in state['batches']}
    if already_submitted:
        info(f"resume mode: {len(already_submitted)} chunks already submitted, will skip")

    timestamp = state['session_timestamp']

    for chunk_idx in range(total_chunks):
        if chunk_idx in already_submitted:
            continue

        start = chunk_idx * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(tasks))
        chunk_tasks = tasks[start:end]
        info(f"--- chunk {chunk_idx + 1}/{total_chunks} ({len(chunk_tasks)} imgs) ---")

        jsonl_file = os.path.join(BATCH_FOLDER, f"chunk{chunk_idx}_{timestamp}.jsonl")
        task_map_file = os.path.join(BATCH_FOLDER, f"taskmap{chunk_idx}_{timestamp}.json")

        if not write_batch_jsonl(chunk_tasks, jsonl_file):
            err(f"skipping chunk {chunk_idx} due to JSONL write failure")
            continue

        try:
            with open(task_map_file, 'w') as f:
                json.dump([{'out': t['out'], 'out_dir': t['out_dir'], 'fname': t['fname']}
                           for t in chunk_tasks], f)
        except Exception as e:
            err(f"could not write task map {task_map_file}", e)
            continue

        file_name = upload_with_retry(jsonl_file)
        if not file_name:
            err(f"chunk {chunk_idx}: upload failed after all retries, skipping")
            continue

        batch_name = submit_with_retry(file_name, chunk_idx)
        if not batch_name:
            err(f"chunk {chunk_idx}: submit failed after all retries, skipping")
            continue

        state['batches'].append({
            'chunk_idx': chunk_idx,
            'batch_name': batch_name,
            'task_map_file': task_map_file,
            'submitted_at': now_iso(),
            'status': 'pending',
            'completed_at': None,
        })
        save_state(state)
        info(f"chunk {chunk_idx + 1}/{total_chunks} submitted + state saved")

        if chunk_idx < total_chunks - 1:
            time.sleep(INTER_SUBMIT_DELAY)

    info(f"submission phase done: {len(state['batches'])} batches active")

# ============================================================================
# Polling loop
# ============================================================================

def poll_loop(state):
    """Poll all pending batches until done. Crash-safe via state file."""
    info("entering polling loop. safe to leave running. ctrl+c to exit, re-run script to resume.")
    info(f"poll interval: {POLL_INTERVAL}s")

    total_success, total_failed = 0, 0
    poll_count = 0
    start_time = datetime.now(timezone.utc)

    while True:
        poll_count += 1
        pending = [b for b in state['batches'] if b['status'] == 'pending']
        if not pending:
            break

        elapsed_total = int((datetime.now(timezone.utc) - start_time).total_seconds())
        h = elapsed_total // 3600
        m = (elapsed_total % 3600) // 60
        info(f"poll #{poll_count} | {len(pending)}/{len(state['batches'])} pending | total elapsed {h}h {m}m")

        for batch_info in pending:
            try:
                batch = client.batches.get(name=batch_info['batch_name'])
                state_str = str(batch.state)
                elapsed = elapsed_since(batch_info['submitted_at'])

                if 'SUCCEEDED' in state_str:
                    info(f"  ok chunk {batch_info['chunk_idx'] + 1} SUCCEEDED after {elapsed}, downloading...")
                    temp_dl = os.path.join(LOG_FOLDER, f"batch_dl_chunk{batch_info['chunk_idx']}.jsonl")

                    if not download_with_retry(batch.dest.file_name, temp_dl):
                        err(f"chunk {batch_info['chunk_idx']}: download failed, will retry next poll")
                        continue

                    try:
                        with open(batch_info['task_map_file']) as f:
                            task_map = json.load(f)
                    except Exception as e:
                        err(f"could not load task map {batch_info['task_map_file']}", e)
                        continue

                    s, fl, failed_list = process_batch_results(temp_dl, task_map)
                    total_success += s
                    total_failed += fl
                    info(f"  chunk {batch_info['chunk_idx'] + 1}: ok {s} saved | fail {fl}")

                    if failed_list:
                        failed_log = os.path.join(LOG_FOLDER,
                            f"failed_chunk{batch_info['chunk_idx']}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt")
                        with open(failed_log, 'w') as f:
                            f.write('\n'.join(failed_list))
                        warn(f"  {len(failed_list)} failures logged to {failed_log}")

                    batch_info['status'] = 'downloaded'
                    batch_info['completed_at'] = now_iso()
                    batch_info['success_count'] = s
                    batch_info['failed_count'] = fl
                    save_state(state)

                    if os.path.exists(temp_dl):
                        os.remove(temp_dl)

                elif 'FAILED' in state_str:
                    err(f"chunk {batch_info['chunk_idx'] + 1} batch FAILED after {elapsed} (state={state_str})")
                    batch_info['status'] = 'failed'
                    batch_info['completed_at'] = now_iso()
                    save_state(state)

                elif 'CANCELLED' in state_str:
                    err(f"chunk {batch_info['chunk_idx'] + 1} batch CANCELLED after {elapsed}")
                    batch_info['status'] = 'cancelled'
                    batch_info['completed_at'] = now_iso()
                    save_state(state)

                else:
                    if POLL_HEARTBEAT:
                        info(f"  chunk {batch_info['chunk_idx'] + 1}: {state_str} ({elapsed} elapsed)")

            except Exception as e:
                warn(f"poll error for chunk {batch_info['chunk_idx']}: {e}", e)

        still_pending = [b for b in state['batches'] if b['status'] == 'pending']
        if still_pending:
            time.sleep(POLL_INTERVAL)

    info("all batches resolved.")
    return total_success, total_failed

# ============================================================================
# Main
# ============================================================================

def print_summary(state):
    info("=" * 60)
    info("BATCH SUMMARY")
    counts = {}
    for b in state['batches']:
        counts[b['status']] = counts.get(b['status'], 0) + 1
    for status, c in counts.items():
        info(f"  {status}: {c}")
    info("=" * 60)

def main():
    print("=" * 60)
    print("AI Image Generation Pipeline - BATCH MODE")
    print(f"Model: {GEMINI_MODEL}")
    print("=" * 60)

    if not API_KEY or not client:
        err("api key missing - put your raw key as only contents of apikey.txt")
        return

    info("verifying api key (free)...")
    ok, msg = verify_api_key()
    if ok:
        info(f"ok {msg}")
    else:
        err(msg)
        return

    if not os.path.exists(INPUT_FOLDER):
        err(f"{INPUT_FOLDER} not found")
        return

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    shot_cfg, cat_cfg = load_config()
    if not shot_cfg or not cat_cfg:
        return

    state = load_state()
    if state:
        # empty state file = leftover garbage from previous abort. just delete it.
        if not state.get('batches'):
            info("found empty state file (leftover from prior abort) - removing")
            try:
                os.remove(STATE_FILE)
            except Exception as e:
                warn(f"could not remove empty state file: {e}", e)
            state = None
        else:
            info(f"found existing state file with {len(state['batches'])} batches")
            info(f"  session: {state['session_timestamp']}")
            print_summary(state)
            choice = input("\n[R]esume existing batches, [N]ew run (archive state), or [Q]uit? ").strip().lower()
            if choice == 'q':
                return
            if choice == 'n':
                os.rename(STATE_FILE, STATE_FILE + ".archived." + datetime.now().strftime('%Y%m%d-%H%M%S'))
                state = None

    if state is None:
        # IN MEMORY ONLY - do NOT write to disk until a batch is actually submitted
        state = {
            'session_timestamp': datetime.now().strftime('%Y%m%d-%H%M%S'),
            'model': GEMINI_MODEL,
            'batches': [],
        }
        # (no save_state() here - was the bug)

    info("scanning inputs and building task list...")
    tasks, skipped = build_tasks(shot_cfg, cat_cfg, VARIANTS_PRODUCTION)
    info(f"already complete on disk: {skipped}")
    info(f"to generate: {len(tasks)}")

    pending = [b for b in state['batches'] if b['status'] == 'pending']
    if not tasks and not pending:
        info("nothing to do!")
        return

    if tasks:
        c = calculate_costs(tasks)

        if len(pending) == 0:
            print()
            print("=" * 60)
            print("COST ESTIMATE (derived from actual data + Google rates)")
            print("=" * 60)
            print(f"  images to generate:     {c['n']}")
            print(f"  model:                  {GEMINI_MODEL}")
            print(f"  resolution:             {DEFAULT_IMAGE_SIZE}")
            print(f"  avg prompt tokens:      {c['avg_prompt_tokens']} (measured from your actual prompts)")
            print(f"  output tokens/img:      {c['output_tokens_each']} (fixed by Google for {DEFAULT_IMAGE_SIZE})")
            print(f"  input image tokens:     {TOKENS_PER_INPUT_IMAGE} (fixed by Google)")
            print()
            print(f"  rates (batch tier, $/M tokens):")
            print(f"    text input:    ${TEXT_INPUT_RATE_PER_M:.2f}/M")
            print(f"    image input:   ${IMAGE_INPUT_RATE_PER_M:.2f}/M")
            print(f"    image output:  ${IMAGE_OUTPUT_RATE_PER_M:.2f}/M")
            print()
            print(f"  cost breakdown:")
            print(f"    text prompts:   ${c['text_cost']:>8,.2f}  ({c['total_prompt_tokens']:,} tokens)")
            print(f"    input images:   ${c['img_in_cost']:>8,.2f}  ({c['n'] * TOKENS_PER_INPUT_IMAGE:,} tokens)")
            print(f"    output images:  ${c['img_out_cost']:>8,.2f}  ({c['n'] * c['output_tokens_each']:,} tokens)")
            print(f"    {'-'*40}")
            print(f"    TOTAL (batch):  ${c['total_batch']:>8,.2f}")
            print(f"    per-image avg:  ${c['per_img_batch']:.4f}")
            print()
            print(f"  reference: real-time API would be ~${c['total_realtime']:,.2f} (2x batch)")
            print("=" * 60)
            print()
            print("monitor live spend: https://aistudio.google.com/usage")
            print()

            confirm1 = input(f"submit {c['n']} images for ~${c['total_batch']:,.2f}? [y/N]: ").strip().lower()
            if confirm1 != 'y':
                info("aborted by user (first confirmation) - no state file written, no charges")
                return

            print()
            print(f"  *** FINAL CONFIRM: this will charge approximately ${c['total_batch']:,.2f}")
            print(f"      to the billing account linked to your api key.")
            confirm2 = input(f"      type YES (uppercase) to proceed: ").strip()
            if confirm2 != 'YES':
                info("aborted by user (second confirmation) - no state file written, no charges")
                return

            info("confirmed, beginning submission...")
            # state file gets created here for the first time, only as batches actually submit
            copy_originals(tasks)
            submit_all_chunks(tasks, state)
        else:
            info(f"existing pending batches detected - skipping new submission, going to polling")
    else:
        info(f"resuming polling of {len(pending)} pending batches (no new work)")

    success, failed = poll_loop(state)

    print()
    print("=" * 60)
    print(f"COMPLETE: ok {success} generated | fail {failed} failed")
    print(f"Output: {OUTPUT_FOLDER}/")
    print(f"Errors log: {ERROR_LOG}")
    print("=" * 60)
    print_summary(state)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        info("interrupted by user. state saved. re-run script to resume.")
    except Exception as e:
        err("fatal error in main", e)
        raise