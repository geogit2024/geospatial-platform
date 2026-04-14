"""
End-to-end pipeline test.
Usage:  py -3 test_pipeline.py <file_path>
"""

import sys
import time
import json
import os
import urllib.request
import urllib.parse
import urllib.error

FILE_PATH  = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\HP\Downloads\69dadc5f7405c8b660856fa1.tif"
API_BASE   = "https://api-production-0f3d2.up.railway.app/api"
POLL_SEC   = 5
TIMEOUT    = 300   # seconds to wait for published status

FILENAME   = os.path.basename(FILE_PATH)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _req(method, path, body=None):
    url  = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def _put_file(upload_url, file_path):
    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as f:
        req = urllib.request.Request(
            upload_url, data=f, method="PUT",
            headers={"Content-Type": "image/tiff", "Content-Length": str(file_size)},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def ok(msg):   print(f"  [OK]   {msg}")
def info(msg): print(f"  [..]   {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def err(msg):  print(f"  [ERR]  {msg}")

# ─── Stage 1: Request signed upload URL ───────────────────────────────────────

section("STAGE 1 — Request signed upload URL")
status, resp = _req("POST", "/upload/signed-url", {"filename": FILENAME, "content_type": "image/tiff"})
if status != 201:
    err(f"HTTP {status}: {resp}")
    sys.exit(1)

image_id   = resp["image_id"]
upload_url = resp["upload_url"]
raw_key    = resp["raw_key"]
ok(f"image_id   = {image_id}")
ok(f"raw_key    = {raw_key}")
info(f"upload_url = {upload_url[:80]}...")

# ─── Stage 2: Upload file ─────────────────────────────────────────────────────

section("STAGE 2 — Upload file to MinIO")
info(f"File: {FILE_PATH}  ({os.path.getsize(FILE_PATH)/1024/1024:.1f} MB)")
t0 = time.time()
put_status = _put_file(upload_url, FILE_PATH)
elapsed = time.time() - t0
ok(f"PUT {put_status}  in {elapsed:.1f}s")

# ─── Stage 3: Confirm upload (triggers worker) ────────────────────────────────

section("STAGE 3 — Confirm upload (enqueue pipeline)")
status, resp = _req("POST", "/upload/confirm", {"image_id": image_id})
if status not in (200, 202):
    err(f"HTTP {status}: {resp}")
    sys.exit(1)
ok(f"Status: {resp.get('status')}  |  message: {resp.get('message')}")

# ─── Stage 4: Poll until published or error ───────────────────────────────────

section("STAGE 4 — Polling pipeline status")
deadline = time.time() + TIMEOUT
prev_status = None

while time.time() < deadline:
    st, img = _req("GET", f"/images/{image_id}")
    if st != 200:
        err(f"GET /images/{image_id} → HTTP {st}")
        break

    cur = img["status"]
    if cur != prev_status:
        info(f"[{time.strftime('%H:%M:%S')}] status = {cur}")
        prev_status = cur

    if cur == "published":
        section("STAGE 5 — Results")
        ok("Layer published successfully")
        print()
        print(f"  image_id   : {img['id']}")
        print(f"  layer_name : {img['layer_name']}")
        print(f"  CRS        : {img['crs']}")
        if img.get("bbox"):
            b = img["bbox"]
            print(f"  bbox (WGS84): {b['minx']:.4f},{b['miny']:.4f} -> {b['maxx']:.4f},{b['maxy']:.4f}")
        print()
        print(f"  WMS  URL   : {img['wms_url']}")
        print(f"  WMTS URL   : {img['wmts_url']}")
        print(f"  WCS  URL   : {img['wcs_url']}")

        # Quick WMS GetCapabilities check
        section("STAGE 6 — WMS GetCapabilities check")
        cap_url = f"{img['wms_url']}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities"
        info(f"GET {cap_url[:80]}...")
        try:
            with urllib.request.urlopen(cap_url, timeout=20) as r:
                body = r.read(200)
                if b"WMS_Capabilities" in body or b"WMT_MS_Capabilities" in body:
                    ok("GetCapabilities returned valid WMS XML")
                else:
                    warn(f"Unexpected response start: {body[:120]}")
        except Exception as e:
            warn(f"GetCapabilities error: {e}")

        print()
        ok("END-TO-END TEST PASSED"  )
        sys.exit(0)

    if cur == "error":
        err(f"Pipeline error: {img.get('error_message')}")
        sys.exit(1)

    time.sleep(POLL_SEC)

err(f"Timeout after {TIMEOUT}s — last status: {prev_status}")
sys.exit(1)
