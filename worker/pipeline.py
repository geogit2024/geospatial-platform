"""
GDAL raster processing pipeline.

Stages
------
  1. audit_raster     — inspect and validate; detects CRS / bbox / nodata issues
  2. normalize_raster — assign CRS → reproject to EPSG:3857 → set NoData → COG
  3. get_raster_metadata — extract spatial metadata for DB + GeoServer

Backward-compatible shims (kept for any code that imports them directly):
  reproject / build_overviews / to_cog
"""

import os
import logging
from typing import Optional

from osgeo import gdal, osr

gdal.UseExceptions()
log = logging.getLogger("worker.pipeline")

# ─── Internal helpers ──────────────────────────────────────────────────────────

def _get_epsg(ds) -> Optional[str]:
    """Return 'EPSG:XXXX' string or None from an open GDAL dataset."""
    wkt = ds.GetProjection()
    if not wkt:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    srs.AutoIdentifyEPSG()
    code = srs.GetAuthorityCode(None)
    return f"EPSG:{code}" if code else None


def _bbox_from_ds(ds) -> Optional[dict]:
    """Extract native bounding box from an open GDAL dataset."""
    gt = ds.GetGeoTransform()
    # Identity geotransform means no georeferencing
    if gt == (0.0, 1.0, 0.0, 0.0, 0.0, 1.0):
        return None
    xmin = gt[0]
    ymax = gt[3]
    xmax = xmin + gt[1] * ds.RasterXSize
    ymin = ymax + gt[5] * ds.RasterYSize
    return {"minx": xmin, "miny": ymin, "maxx": xmax, "maxy": ymax}


def transform_bbox_to_wgs84(bbox: dict, src_crs: str) -> dict:
    """
    Transform a bbox from src_crs to WGS84 lon/lat (EPSG:4326).
    Uses OAMS_TRADITIONAL_GIS_ORDER so X=lon, Y=lat in both input and output.
    """
    src = osr.SpatialReference()
    src.SetFromUserInput(src_crs)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    ct = osr.CoordinateTransformation(src, dst)
    lon1, lat1, _ = ct.TransformPoint(bbox["minx"], bbox["miny"])
    lon2, lat2, _ = ct.TransformPoint(bbox["maxx"], bbox["maxy"])
    return {
        "minx": min(lon1, lon2),
        "miny": min(lat1, lat2),
        "maxx": max(lon1, lon2),
        "maxy": max(lat1, lat2),
    }


# ─── Stage 1: Audit ───────────────────────────────────────────────────────────

def audit_raster(path: str) -> dict:
    """
    Inspect a raster file and report validation issues.

    Returns a structured dict; ``issues`` is an empty list if the file is clean.
    Always logs a summary at INFO level and warnings for each issue found.
    """
    result: dict = {
        "path":       path,
        "issues":     [],
        "epsg":       None,
        "bbox":       None,
        "pixel_size": None,
        "nodata":     None,
        "band_count": None,
        "data_type":  None,
        "width":      None,
        "height":     None,
    }

    ds = gdal.Open(path)
    if ds is None:
        result["issues"].append("GDAL cannot open file")
        log.error("[audit] Cannot open: %s", path)
        return result

    result["band_count"] = ds.RasterCount
    result["width"]      = ds.RasterXSize
    result["height"]     = ds.RasterYSize

    b1 = ds.GetRasterBand(1)
    result["data_type"] = gdal.GetDataTypeName(b1.DataType)
    nodata = b1.GetNoDataValue()
    result["nodata"] = nodata
    if nodata is None:
        result["issues"].append("NoData not defined")
        log.warning("[audit] NoData not defined: %s", path)

    # ── CRS ────────────────────────────────────────────────────────────────────
    epsg = _get_epsg(ds)
    result["epsg"] = epsg
    if not ds.GetProjection():
        result["issues"].append("CRS missing")
        log.warning("[audit] CRS missing: %s", path)
    elif epsg not in ("EPSG:4326", "EPSG:3857"):
        result["issues"].append(f"Non-standard EPSG: {epsg}")
        log.warning("[audit] Non-standard EPSG %s: %s", epsg, path)

    # ── Geotransform / Bbox ────────────────────────────────────────────────────
    bbox = _bbox_from_ds(ds)
    if bbox is None:
        result["issues"].append("Geotransform missing — raster has no georeferencing")
        log.warning("[audit] Missing geotransform: %s", path)
    else:
        result["bbox"] = bbox
        gt = ds.GetGeoTransform()
        result["pixel_size"] = {"x": abs(gt[1]), "y": abs(gt[5])}

        if epsg == "EPSG:4326" and not (
            -180 <= bbox["minx"] <= 180 and -90 <= bbox["miny"] <= 90
        ):
            result["issues"].append(f"Bbox out of EPSG:4326 range: {bbox}")
            log.warning("[audit] Bbox out of WGS84 range — %s: %s", path, bbox)

    ds = None

    if result["issues"]:
        log.info("[audit] %s — %d issue(s): %s", path, len(result["issues"]), result["issues"])
    else:
        log.info(
            "[audit] %s — OK  epsg=%s  bands=%d  size=%dx%d",
            path, epsg, result["band_count"], result["width"], result["height"],
        )
    return result


# ─── Stage 2: Normalize ───────────────────────────────────────────────────────

def normalize_raster(
    src_path: str,
    dst_path: str,
    assume_epsg: str = "EPSG:4326",
    nodata_value: float = 0,
) -> None:
    """
    Full normalization pipeline that produces a publication-ready COG:

    1. Assign CRS if missing (default: ``assume_epsg``)
    2. Reproject to EPSG:3857 (Web Mercator) with bilinear resampling
    3. Set NoData = ``nodata_value``
    4. Generate Cloud Optimized GeoTIFF (DEFLATE, 512×512 tiles, auto-overviews)

    Intermediate temp files are written to the same directory as ``dst_path``
    and cleaned up on exit (success or failure).
    """
    tmpdir       = os.path.dirname(dst_path) or "."
    step_assigned = os.path.join(tmpdir, "_norm_assigned.tif")
    step_warped   = os.path.join(tmpdir, "_norm_warped.tif")

    try:
        # ── 1. Assign CRS if missing ───────────────────────────────────────────
        ds = gdal.Open(src_path)
        has_crs = bool(ds.GetProjection())
        ds = None

        if not has_crs:
            log.warning("[normalize] Assigning %s to CRS-less raster", assume_epsg)
            result = gdal.Translate(
                step_assigned, src_path,
                options=gdal.TranslateOptions(outputSRS=assume_epsg),
            )
            if result is None:
                raise RuntimeError(f"CRS assignment ({assume_epsg}) failed for {src_path}")
            result = None
            reproj_src = step_assigned
        else:
            reproj_src = src_path

        # ── 2. Reproject to EPSG:3857 ──────────────────────────────────────────
        log.info("[normalize] Reprojecting → EPSG:3857")
        warp_opts = gdal.WarpOptions(
            dstSRS="EPSG:3857",
            resampleAlg=gdal.GRA_Bilinear,
            creationOptions=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
            dstNodata=nodata_value,
            multithread=True,
            warpMemoryLimit=512,
        )
        result = gdal.Warp(step_warped, reproj_src, options=warp_opts)
        if result is None:
            raise RuntimeError(f"Reprojection to EPSG:3857 failed for {reproj_src}")
        result = None

        # ── 3 + 4. Set NoData + generate COG ──────────────────────────────────
        log.info("[normalize] Generating COG (DEFLATE, 512×512 tiles)")
        cog_opts = gdal.TranslateOptions(
            format="COG",
            noData=nodata_value,
            creationOptions=[
                "COMPRESS=DEFLATE",
                "PREDICTOR=2",
                "TILED=YES",
                "BLOCKXSIZE=512",
                "BLOCKYSIZE=512",
                "OVERVIEW_RESAMPLING=AVERAGE",
                "BIGTIFF=IF_SAFER",
            ],
        )
        result = gdal.Translate(dst_path, step_warped, options=cog_opts)
        if result is None:
            raise RuntimeError(f"COG generation failed → {dst_path}")
        result = None

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
    Extract CRS and bounding boxes from a normalized COG.

    Returns::

        {
          "crs":       "EPSG:3857",
          "bbox":      {minx, miny, maxx, maxy},  # native CRS (EPSG:3857 metres)
          "bbox_wgs84":{minx, miny, maxx, maxy},  # WGS84 degrees for display/DB
        }
    """
    ds = gdal.Open(path)
    if ds is None:
        raise RuntimeError(f"Cannot open raster: {path}")

    epsg = _get_epsg(ds)
    if not epsg:
        wkt = ds.GetProjection()
        srs = osr.SpatialReference()
        if wkt:
            srs.ImportFromWkt(wkt)
        epsg = srs.ExportToProj4() or "unknown"

    native_bbox = _bbox_from_ds(ds)
    ds = None

    if native_bbox is None:
        raise RuntimeError(f"Raster has no geotransform (not georeferenced): {path}")

    # Transform to WGS84 for human-readable DB storage
    try:
        wgs84_bbox = transform_bbox_to_wgs84(native_bbox, epsg)
    except Exception as exc:
        log.warning("[metadata] Cannot transform bbox to WGS84: %s — using native", exc)
        wgs84_bbox = native_bbox  # fallback

    return {
        "crs":       epsg,
        "bbox":      native_bbox,
        "bbox_wgs84": wgs84_bbox,
    }


# ─── Backward-compatible shims ────────────────────────────────────────────────

def reproject(src: str, dst: str, target_crs: str = "EPSG:3857") -> None:
    """Reproject raster. Retained for backward compatibility."""
    opts = gdal.WarpOptions(
        dstSRS=target_crs,
        resampleAlg=gdal.GRA_Bilinear,
        creationOptions=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
        multithread=True,
    )
    result = gdal.Warp(dst, src, options=opts)
    if result is None:
        raise RuntimeError(f"reproject: {src} → {target_crs} failed")
    result = None


def build_overviews(path: str, levels: Optional[list] = None) -> None:
    """Build internal overviews. Retained for backward compatibility."""
    if levels is None:
        levels = [2, 4, 8, 16, 32, 64]
    ds = gdal.Open(path, gdal.GA_Update)
    if ds is None:
        raise RuntimeError(f"build_overviews: cannot open {path}")
    ds.BuildOverviews("AVERAGE", levels)
    ds = None
    log.info("[pipeline] Overviews built: %s", path)


def to_cog(src: str, dst: str) -> None:
    """Convert to COG. Retained for backward compatibility."""
    opts = gdal.TranslateOptions(
        format="COG",
        creationOptions=[
            "COMPRESS=DEFLATE",
            "TILED=YES",
            "BLOCKXSIZE=512",
            "BLOCKYSIZE=512",
            "COPY_SRC_OVERVIEWS=YES",
            "BIGTIFF=IF_SAFER",
        ],
    )
    result = gdal.Translate(dst, src, options=opts)
    if result is None:
        raise RuntimeError(f"to_cog: {src} → {dst} failed")
    result = None
    log.info("[pipeline] COG written: %s", dst)
