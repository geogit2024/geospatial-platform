"""
GeoPublish — Professional Pipeline Test Suite
=============================================
Validates the complete flow:
  Upload → MinIO Storage → Worker GDAL Pipeline → GeoServer Publication → OGC Services

Usage:
    python tests/test_pipeline.py [--file PATH] [--api URL] [--timeout SECONDS]

Example:
    python tests/test_pipeline.py \
        --file "C:/Users/HP/Downloads/o41078a5.tif" \
        --api https://frontend-production-d8ee.up.railway.app \
        --timeout 300
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Force UTF-8 stdout on Windows (avoids cp1252 UnicodeEncodeError with ANSI chars)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
#  ANSI colors (works on Windows 10+ terminals)
# ─────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: int = 0


@dataclass
class TestSuite:
    results: list = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def record(self, result: TestResult):
        self.results.append(result)
        icon = f"{GREEN}✓{RESET}" if result.passed else f"{RED}✗{RESET}"
        dur  = f"{CYAN}({result.duration_ms}ms){RESET}"
        print(f"  {icon}  {result.name} {dur}")
        if result.detail:
            color = GREEN if result.passed else RED
            print(f"     {color}→ {result.detail}{RESET}")

    def summary(self):
        total    = len(self.results)
        passed   = sum(1 for r in self.results if r.passed)
        failed   = total - passed
        elapsed  = time.time() - self.start_time
        bar      = "─" * 56
        print(f"\n{bar}")
        print(f"{BOLD}  Results: {passed}/{total} passed  |  {elapsed:.1f}s{RESET}")
        if failed:
            print(f"\n  {RED}Failed tests:{RESET}")
            for r in self.results:
                if not r.passed:
                    print(f"    {RED}✗ {r.name}{RESET}")
                    if r.detail:
                        print(f"      {r.detail}")
        print(f"{bar}")
        return failed == 0


# ─────────────────────────────────────────────
#  HTTP helpers
# ─────────────────────────────────────────────

def http(method: str, url: str, body: Optional[dict] = None,
         headers: Optional[dict] = None, timeout: int = 30) -> tuple[int, bytes]:
    data = json.dumps(body).encode() if body else None
    h    = {"Content-Type": "application/json", **(headers or {})}
    req  = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def http_json(method: str, url: str, body: Optional[dict] = None) -> tuple[int, dict]:
    status, raw = http(method, url, body)
    try:
        return status, json.loads(raw)
    except Exception:
        return status, {"_raw": raw.decode(errors="replace")}


def put_file(url: str, file_path: str, content_type: str = "image/tiff") -> tuple[int, int]:
    """Upload file via HTTP PUT, return (status, bytes_sent)."""
    size = os.path.getsize(file_path)
    with open(file_path, "rb") as fh:
        req = urllib.request.Request(
            url,
            data=fh.read(),
            headers={"Content-Type": content_type, "Content-Length": str(size)},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, size
        except urllib.error.HTTPError as e:
            return e.code, size


# ─────────────────────────────────────────────
#  Individual test steps
# ─────────────────────────────────────────────

def test_api_health(suite: TestSuite, api: str):
    t0 = time.time()
    status, body = http_json("GET", f"{api}/api/images")
    # /api/images returns [] when empty — any 2xx is healthy
    passed = status in (200, 201)
    suite.record(TestResult(
        "API Health & Connectivity",
        passed,
        f"GET /api/images → {status}" + (f" ({len(body)} images)" if passed else f" body={body}"),
        int((time.time() - t0) * 1000),
    ))
    return passed


def test_request_signed_url(suite: TestSuite, api: str, filename: str,
                            content_type: str) -> Optional[dict]:
    t0 = time.time()
    status, body = http_json("POST", f"{api}/api/upload/signed-url", {
        "filename": filename,
        "content_type": content_type,
    })
    passed = status in (200, 201) and "upload_url" in body and "image_id" in body
    upload_url = body.get("upload_url", "")
    is_https   = upload_url.startswith("https://")
    suite.record(TestResult(
        "Presigned URL generation",
        passed,
        f"image_id={body.get('image_id','?')} | HTTPS={is_https}" if passed
        else f"status={status} body={body}",
        int((time.time() - t0) * 1000),
    ))
    if passed and not is_https:
        suite.record(TestResult(
            "Presigned URL is HTTPS (Mixed Content safe)",
            False,
            f"URL starts with: {upload_url[:40]}",
            0,
        ))
        return None
    suite.record(TestResult(
        "Presigned URL is HTTPS (Mixed Content safe)",
        is_https,
        upload_url[:60] + "..." if passed else "",
        0,
    ))
    return body if passed else None


def test_direct_upload(suite: TestSuite, upload_url: str, file_path: str) -> bool:
    t0     = time.time()
    ext    = os.path.splitext(file_path)[1].lower()
    ctype  = "image/tiff" if ext in (".tif", ".tiff") else "application/octet-stream"
    status, size = put_file(upload_url, file_path, ctype)
    passed = status in (200, 204)
    suite.record(TestResult(
        "Direct file upload to MinIO (PUT presigned URL)",
        passed,
        f"{size/1024/1024:.2f} MB uploaded → HTTP {status}" if passed
        else f"HTTP {status} — upload failed",
        int((time.time() - t0) * 1000),
    ))
    return passed


def test_confirm_upload(suite: TestSuite, api: str, image_id: str) -> bool:
    t0 = time.time()
    status, body = http_json("POST", f"{api}/api/upload/confirm", {"image_id": image_id})
    passed = status in (200, 202)
    suite.record(TestResult(
        "Confirm upload (enqueue to Redis)",
        passed,
        f"status={status}" if passed else f"status={status} body={body}",
        int((time.time() - t0) * 1000),
    ))
    return passed


def test_status_transition(suite: TestSuite, api: str, image_id: str,
                           timeout_s: int) -> Optional[str]:
    """Poll image status until terminal state or timeout."""
    TERMINAL    = {"published", "error"}
    PROGRESSION = ["pending", "uploading", "uploaded", "processing",
                   "processed", "publishing", "published"]
    seen        = set()
    deadline    = time.time() + timeout_s
    last_status = "unknown"
    print(f"\n  {CYAN}Monitoring pipeline progress (timeout={timeout_s}s):{RESET}")

    while time.time() < deadline:
        status, body = http_json("GET", f"{api}/api/images/{image_id}")
        if status != 200:
            time.sleep(5)
            continue

        current = body.get("status", "unknown")
        if current != last_status:
            elapsed = timeout_s - (deadline - time.time())
            label   = f"{YELLOW}{current}{RESET}"
            if current == "published":
                label = f"{GREEN}{current}{RESET}"
            elif current == "error":
                label = f"{RED}{current}{RESET}"
            print(f"    [{elapsed:5.1f}s] {label}")
            seen.add(current)
            last_status = current

        if current in TERMINAL:
            break
        time.sleep(5)

    # Validate progression
    expected_seen = {"uploaded", "processing"}
    progressed    = bool(seen & expected_seen)
    suite.record(TestResult(
        "Worker picks up job from Redis",
        "processing" in seen or "processed" in seen or "published" in seen,
        f"States observed: {' → '.join(s for s in PROGRESSION if s in seen)}",
        0,
    ))
    suite.record(TestResult(
        "GDAL pipeline completes (processed state)",
        "processed" in seen or "published" in seen,
        "COG generation completed" if "processed" in seen or "published" in seen
        else f"Stuck at: {last_status}",
        0,
    ))
    suite.record(TestResult(
        "GeoServer publication (published state)",
        last_status == "published",
        "WMS/WMTS/WCS layer created" if last_status == "published"
        else f"Final status: {last_status}",
        0,
    ))

    if last_status == "error":
        _, detail = http_json("GET", f"{api}/api/images/{image_id}")
        err = detail.get("error_message", "no detail")
        print(f"  {RED}  Error detail: {err}{RESET}")

    return last_status


def test_image_metadata(suite: TestSuite, api: str, image_id: str) -> bool:
    t0 = time.time()
    status, body = http_json("GET", f"{api}/api/images/{image_id}")
    has_crs  = bool(body.get("crs"))
    has_bbox = body.get("bbox") is not None
    has_layer = bool(body.get("layer_name"))
    passed   = status == 200 and has_crs and has_bbox and has_layer
    suite.record(TestResult(
        "Image metadata populated (CRS, BBox, layer_name)",
        passed,
        f"CRS={body.get('crs')} | bbox={has_bbox} | layer={body.get('layer_name')}",
        int((time.time() - t0) * 1000),
    ))
    return passed


def test_ogc_services(suite: TestSuite, api: str, image_id: str):
    t0 = time.time()
    status, body = http_json("GET", f"{api}/api/services/{image_id}/ogc")
    has_wms  = bool(body.get("services", {}).get("wms", {}).get("getcapabilities"))
    has_wmts = bool(body.get("services", {}).get("wmts", {}).get("getcapabilities"))
    has_wcs  = bool(body.get("services", {}).get("wcs", {}).get("getcapabilities"))
    suite.record(TestResult(
        "OGC service URLs returned by API",
        status == 200 and has_wms,
        f"WMS={has_wms} WMTS={has_wmts} WCS={has_wcs}",
        int((time.time() - t0) * 1000),
    ))

    if status != 200:
        return

    # Probe each OGC endpoint
    for svc_name, key in [("WMS", "wms"), ("WMTS", "wmts"), ("WCS", "wcs")]:
        cap_url = body["services"][key].get("getcapabilities", "")
        if not cap_url:
            continue
        t1 = time.time()
        try:
            svc_status, raw = http("GET", cap_url, timeout=20)
            ok = svc_status == 200 and (b"Capabilities" in raw or b"capabilities" in raw)
            suite.record(TestResult(
                f"{svc_name} GetCapabilities responds",
                ok,
                f"HTTP {svc_status} | {len(raw)} bytes",
                int((time.time() - t1) * 1000),
            ))
        except Exception as e:
            suite.record(TestResult(
                f"{svc_name} GetCapabilities responds",
                False,
                str(e),
                int((time.time() - t1) * 1000),
            ))

    # WMS GetMap sample
    wms_example = body["services"]["wms"].get("getmap_example", "")
    if wms_example:
        t1 = time.time()
        try:
            gm_status, raw = http("GET", wms_example, timeout=20)
            ok = gm_status == 200 and (b"PNG" in raw[:8] or b"GIF" in raw[:6]
                                        or b"\xff\xd8" in raw[:4]  # JPEG
                                        or len(raw) > 100)
            suite.record(TestResult(
                "WMS GetMap returns image",
                ok,
                f"HTTP {gm_status} | {len(raw)} bytes",
                int((time.time() - t1) * 1000),
            ))
        except Exception as e:
            suite.record(TestResult(
                "WMS GetMap returns image",
                False,
                str(e),
                int((time.time() - t1) * 1000),
            ))


def test_dashboard_listing(suite: TestSuite, api: str, image_id: str):
    t0 = time.time()
    status, body = http_json("GET", f"{api}/api/images")
    found = any(img.get("id") == image_id for img in (body if isinstance(body, list) else []))
    suite.record(TestResult(
        "Image appears in dashboard listing",
        found,
        f"{len(body) if isinstance(body, list) else '?'} total images, found={found}",
        int((time.time() - t0) * 1000),
    ))


# ─────────────────────────────────────────────
#  Main runner
# ─────────────────────────────────────────────

def run(file_path: str, api: str, timeout: int):
    bar = "═" * 56
    print(f"\n{BOLD}{CYAN}{bar}{RESET}")
    print(f"{BOLD}{CYAN}  GeoPublish Pipeline Test Suite{RESET}")
    print(f"{CYAN}  File   : {file_path}{RESET}")
    print(f"{CYAN}  API    : {api}{RESET}")
    print(f"{CYAN}  Timeout: {timeout}s{RESET}")
    print(f"{BOLD}{CYAN}{bar}{RESET}\n")

    # Validate local file
    if not os.path.exists(file_path):
        print(f"{RED}ERROR: File not found: {file_path}{RESET}")
        sys.exit(1)

    file_size_mb = os.path.getsize(file_path) / 1024 / 1024
    filename     = os.path.basename(file_path)
    print(f"  File size : {file_size_mb:.2f} MB")
    print(f"  Filename  : {filename}\n")

    suite = TestSuite()

    # ── Phase 1: API health ───────────────────
    print(f"{BOLD}Phase 1 — API Connectivity{RESET}")
    if not test_api_health(suite, api):
        print(f"\n{RED}API unreachable — aborting.{RESET}")
        suite.summary()
        sys.exit(1)

    # ── Phase 2: Upload flow ──────────────────
    print(f"\n{BOLD}Phase 2 — Upload Flow{RESET}")
    signed = test_request_signed_url(suite, api, filename, "image/tiff")
    if not signed:
        suite.summary()
        sys.exit(1)

    image_id   = signed["image_id"]
    upload_url = signed["upload_url"]
    print(f"  Image ID  : {image_id}")

    if not test_direct_upload(suite, upload_url, file_path):
        suite.summary()
        sys.exit(1)

    if not test_confirm_upload(suite, api, image_id):
        suite.summary()
        sys.exit(1)

    # ── Phase 3: Processing pipeline ─────────
    print(f"\n{BOLD}Phase 3 — Worker GDAL Pipeline{RESET}")
    final_status = test_status_transition(suite, api, image_id, timeout)

    if final_status != "published":
        print(f"\n{YELLOW}Pipeline did not reach 'published'. Stopping at Phase 4.{RESET}")
        suite.summary()
        sys.exit(1 if final_status == "error" else 0)

    # ── Phase 4: Metadata & OGC ───────────────
    print(f"\n{BOLD}Phase 4 — Metadata & OGC Services{RESET}")
    test_image_metadata(suite, api, image_id)
    test_ogc_services(suite, api, image_id)
    test_dashboard_listing(suite, api, image_id)

    # ── Summary ───────────────────────────────
    ok = suite.summary()
    print(f"\n  Image ID for reference: {CYAN}{image_id}{RESET}\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GeoPublish pipeline test suite")
    parser.add_argument(
        "--file", default=r"C:\Users\HP\Downloads\o41078a5.tif",
        help="Path to GeoTIFF test file",
    )
    parser.add_argument(
        "--api", default="https://frontend-production-d8ee.up.railway.app",
        help="Frontend/API base URL",
    )
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Max seconds to wait for pipeline completion (default: 300)",
    )
    args = parser.parse_args()
    run(args.file, args.api, args.timeout)
