import subprocess
import json


def to_cog(input_path: str, output_path: str) -> str:
    """Convert a GeoTIFF with overviews to Cloud Optimized GeoTIFF (COG)."""
    cmd = [
        "gdal_translate",
        "-of", "COG",
        "-co", "COMPRESS=DEFLATE",
        "-co", "PREDICTOR=2",
        "-co", "TILED=YES",
        "-co", "BLOCKXSIZE=512",
        "-co", "BLOCKYSIZE=512",
        "-co", "COPY_SRC_OVERVIEWS=YES",
        "-co", "RESAMPLING=AVERAGE",
        input_path,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdal_translate (COG) failed: {result.stderr}")
    return output_path


def get_raster_metadata(file_path: str) -> dict:
    """Extract spatial metadata from a raster using gdalinfo."""
    cmd = ["gdalinfo", "-json", file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdalinfo failed: {result.stderr}")

    info = json.loads(result.stdout)

    crs = None
    if "coordinateSystem" in info:
        wkt = info["coordinateSystem"].get("wkt", "")
        if "EPSG" in wkt:
            import re
            match = re.search(r'ID\["EPSG",(\d+)\]', wkt)
            if match:
                crs = f"EPSG:{match.group(1)}"

    bbox = None
    if "wgs84Extent" in info:
        coords = info["wgs84Extent"].get("coordinates", [[]])[0]
        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            bbox = {
                "minx": min(xs),
                "miny": min(ys),
                "maxx": max(xs),
                "maxy": max(ys),
            }

    return {"crs": crs, "bbox": bbox}
