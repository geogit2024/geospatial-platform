"""
GDAL raster processing pipeline.

Uses GDAL CLI tools (gdalwarp, gdal_translate, gdaladdo, gdalinfo) — no Python
GDAL bindings required.  All submodule functions are re-exported from here so
worker.py can do: from pipeline import audit_raster, normalize_raster, ...

Public API
----------
audit_raster(path)                      -> dict
normalize_raster(src, dst)              -> None
get_raster_metadata(path)               -> dict
transform_bbox_to_wgs84(bbox, src_crs)  -> dict

Backward-compat re-exports:
  reproject, build_overviews, to_cog
"""

import json
import logging
import math
import os
import re
import subprocess
import tempfile
from typing import Optional

from pipeline.reproject import reproject
from pipeline.pyramids import build_overviews
from pipeline.cog import to_cog

log = logging.getLogger("worker.pipeline")

_M = 20037508.342789244   # EPSG:3857 semi-major axis in metres


# ─── Coordinate helpers ───────────────────────────────────────────────────────

def transform_bbox_to_wgs84(bbox: dict, src_crs: str = "EPSG:3857") -> dict:
    """Convert an EPSG:3857 bbox (metres) to WGS84 lon/lat. Pure Python math."""
    if "3857" in src_crs or "900913" in src_crs:
        def _x2lon(x: float) -> float:
            return x * 180.0 / _M
        def _y2lat(y: float) -> float:
            return math.degrees(2.0 * math.atan(math.exp(y * math.pi / _M)) - math.pi / 2.0)
        return {
            "minx": _x2lon(bbox["minx"]),
            "miny": _y2lat(bbox["miny"]),
            "maxx": _x2lon(bbox["maxx"]),
            "maxy": _y2lat(bbox["maxy"]),
        }
    log.warning("transform_bbox_to_wgs84: unsupported src_crs=%s, returning native", src_crs)
    return bbox


# ─── gdalinfo helpers ─────────────────────────────────────────────────────────

def _gdalinfo(path: str) -> dict:
    r = subprocess.run(["gdalinfo", "-json", path], capture_output=True, text=True)
    if r.returncode != 0:
        err = r.stderr.strip()
        if path.lower().endswith(".ecw") and "not recognized as a supported file format" in err.lower():
            raise RuntimeError(
                "Formato ECW nao suportado neste ambiente de producao "
                "(driver GDAL ECW ausente). Converta para GeoTIFF (.tif) ou JP2."
            )
        raise RuntimeError(f"gdalinfo failed: {err[:300]}")
    return json.loads(r.stdout)


def _extract_epsg(info: dict) -> Optional[str]:
    """
    Extract the top-level EPSG code from a gdalinfo coordinateSystem WKT.

    A PROJCRS WKT contains multiple ID["EPSG",...] entries (base geographic CRS
    and the projected CRS itself).  We need the LAST one, which corresponds to
    the outermost (overall) CRS — e.g. EPSG:3857, not the embedded EPSG:4326.
    """
    wkt = info.get("coordinateSystem", {}).get("wkt", "")
    if not wkt:
        return None
    matches = re.findall(r'ID\["EPSG",(\d+)\]', wkt)
    return f"EPSG:{matches[-1]}" if matches else None


def _extract_native_bbox(info: dict) -> Optional[dict]:
    cc = info.get("cornerCoordinates", {})
    ll = cc.get("lowerLeft")
    ur = cc.get("upperRight")
    if not ll or not ur:
        return None
    return {"minx": ll[0], "miny": ll[1], "maxx": ur[0], "maxy": ur[1]}


def _extract_nodata(info: dict) -> Optional[float]:
    bands = info.get("bands", [])
    if not bands:
        return None
    nd = bands[0].get("noDataValue")
    return float(nd) if nd is not None else None


def _run(cmd: list, label: str, timeout: int = 600) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{label} timed out after {timeout}s")
    if r.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {r.returncode}): {r.stderr.strip()[:400]}")
    if r.stderr:
        log.debug("[%s] stderr: %s", label, r.stderr.strip()[:200])


def _is_missing_georeference_warp_error(exc: RuntimeError) -> bool:
    """Detect gdalwarp failure for rasters without affine transform/GCPs."""
    message = str(exc).lower()
    return (
        "unable to compute a transformation between pixel/line and georeferenced coordinates" in message
        or "there is no affine transformation and no gcps" in message
    )


# ─── Stage 1: Audit ───────────────────────────────────────────────────────────

def audit_raster(path: str) -> dict:
    """
    Inspect a raster file and report validation issues.
    Returns a dict with an 'issues' list (empty = clean file).
    """
    result: dict = {
        "path": path, "issues": [], "epsg": None, "bbox": None,
        "nodata": None, "band_count": None, "data_type": None,
        "width": None, "height": None,
    }
    try:
        info = _gdalinfo(path)
    except RuntimeError as exc:
        result["issues"].append(str(exc))
        log.error("[audit] %s", exc)
        return result

    result["width"]      = info.get("size", [None, None])[0]
    result["height"]     = info.get("size", [None, None])[1]
    result["band_count"] = len(info.get("bands", []))
    bands = info.get("bands", [])
    if bands:
        result["data_type"] = bands[0].get("type")

    epsg = _extract_epsg(info)
    result["epsg"] = epsg
    if not info.get("coordinateSystem", {}).get("wkt"):
        result["issues"].append("CRS missing")
        log.warning("[audit] CRS missing: %s", path)
    elif epsg not in ("EPSG:4326", "EPSG:3857"):
        result["issues"].append(f"Non-standard EPSG: {epsg}")
        log.warning("[audit] Non-standard EPSG %s: %s", epsg, path)

    nodata = _extract_nodata(info)
    result["nodata"] = nodata
    if nodata is None:
        result["issues"].append("NoData not defined")
        log.warning("[audit] NoData not defined: %s", path)

    bbox = _extract_native_bbox(info)
    if bbox is None:
        result["issues"].append("No georeferencing")
        log.warning("[audit] Missing georeferencing: %s", path)
    else:
        result["bbox"] = bbox
        if epsg == "EPSG:4326" and not (-180 <= bbox["minx"] <= 180 and -90 <= bbox["miny"] <= 90):
            result["issues"].append(f"Bbox out of WGS84 range: {bbox}")
            log.warning("[audit] Bbox out of WGS84 range — %s: %s", path, bbox)

    if result["issues"]:
        log.info("[audit] %s — %d issue(s): %s", path, len(result["issues"]), result["issues"])
    else:
        log.info("[audit] %s — OK  epsg=%s  bands=%d  %dx%d",
                 path, epsg, result["band_count"], result["width"], result["height"])
    return result


# ─── Stage 2: Normalize ───────────────────────────────────────────────────────

def normalize_raster(
    src_path: str,
    dst_path: str,
    assume_epsg: str = "EPSG:4326",
    nodata_value: float = 0,
) -> None:
    """
    Full normalization pipeline:
      1. Assign CRS (assume_epsg) if raster has none
      2. Reproject to EPSG:3857 with bilinear resampling + set NoData
      3. Generate Cloud Optimized GeoTIFF (DEFLATE, 512x512 tiles, auto-overviews)
    """
    tmpdir        = os.path.dirname(dst_path) or tempfile.gettempdir()
    step_assigned = os.path.join(tmpdir, "_norm_assigned.tif")
    step_warped   = os.path.join(tmpdir, "_norm_warped.tif")

    try:
        # 1. Assign CRS if missing
        info    = _gdalinfo(src_path)
        has_crs = bool(info.get("coordinateSystem", {}).get("wkt"))
        if not has_crs:
            log.warning("[normalize] Assigning %s to CRS-less raster", assume_epsg)
            _run(["gdal_translate", "-a_srs", assume_epsg, src_path, step_assigned],
                 "CRS assignment")
            reproj_src = step_assigned
        else:
            reproj_src = src_path

        # 2. Reproject to EPSG:3857
        log.info("[normalize] Reprojecting → EPSG:3857")
        warp_cmd = [
            "gdalwarp",
            "-t_srs",     "EPSG:3857",
            "-r",         "bilinear",
            "-dstnodata", str(nodata_value),
            "-wo",        f"NUM_THREADS={os.cpu_count() or 4}",
            "-co",        "COMPRESS=LZW",
            "-co",        "TILED=YES",
            reproj_src, step_warped,
        ]
        try:
            _run(warp_cmd, "gdalwarp EPSG:3857")
        except RuntimeError as exc:
            if not _is_missing_georeference_warp_error(exc):
                raise

            # Some JPEG/JPG files arrive without affine transform or GCPs.
            # Retry with explicit GDAL override to keep the pipeline flowing.
            log.warning(
                "[normalize] Missing affine transform/GCPs - retrying gdalwarp with SRC_METHOD=NO_GEOTRANSFORM"
            )
            _run([
                "gdalwarp",
                "-t_srs",     "EPSG:3857",
                "-r",         "bilinear",
                "-dstnodata", str(nodata_value),
                "-wo",        f"NUM_THREADS={os.cpu_count() or 4}",
                "-to",        "SRC_METHOD=NO_GEOTRANSFORM",
                "-co",        "COMPRESS=LZW",
                "-co",        "TILED=YES",
                reproj_src, step_warped,
            ], "gdalwarp EPSG:3857 (NO_GEOTRANSFORM)")

        # 3. Generate COG with DEFLATE + NoData
        log.info("[normalize] Generating COG (DEFLATE, 512x512 tiles)")
        _run([
            "gdal_translate",
            "-of",       "COG",
            "-a_nodata", str(nodata_value),
            "-co",       "COMPRESS=DEFLATE",
            "-co",       "PREDICTOR=2",
            "-co",       "TILED=YES",
            "-co",       "BLOCKXSIZE=512",
            "-co",       "BLOCKYSIZE=512",
            "-co",       "OVERVIEW_RESAMPLING=AVERAGE",
            step_warped, dst_path,
        ], "gdal_translate COG")

        log.info("[normalize] Done → %s", dst_path)

    finally:
        for f in (step_assigned, step_warped):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass


# ─── Stage 3: Metadata extraction ────────────────────────────────────────────

def get_raster_metadata(path: str) -> dict:
    """
    Extract CRS and bounding boxes from a raster.

    Returns::
        {
          "crs":        "EPSG:3857",
          "bbox":       {minx, miny, maxx, maxy},   # native CRS
          "bbox_wgs84": {minx, miny, maxx, maxy},   # WGS84 degrees
        }
    """
    info        = _gdalinfo(path)
    epsg        = _extract_epsg(info)
    native_bbox = _extract_native_bbox(info)

    if native_bbox is None:
        # Fallback to wgs84Extent from gdalinfo
        coords = info.get("wgs84Extent", {}).get("coordinates", [[]])[0]
        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            wgs84_bbox = {"minx": min(xs), "miny": min(ys), "maxx": max(xs), "maxy": max(ys)}
            return {"crs": epsg, "bbox": wgs84_bbox, "bbox_wgs84": wgs84_bbox}
        raise RuntimeError(f"Cannot extract bbox from {path}")

    try:
        wgs84_bbox = transform_bbox_to_wgs84(native_bbox, epsg or "EPSG:3857")
    except Exception as exc:
        log.warning("[metadata] bbox transform failed: %s — using native", exc)
        wgs84_bbox = native_bbox

    return {"crs": epsg, "bbox": native_bbox, "bbox_wgs84": wgs84_bbox}
