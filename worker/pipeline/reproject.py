import subprocess
import os


def reproject(input_path: str, output_path: str, target_crs: str = "EPSG:4326") -> str:
    """Reproject a raster to the target CRS using gdalwarp."""
    cmd = [
        "gdalwarp",
        "-t_srs", target_crs,
        "-r", "bilinear",
        "-of", "GTiff",
        "-co", "COMPRESS=LZW",
        "-wo", f"NUM_THREADS={os.cpu_count() or 4}",
        input_path,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdalwarp failed: {result.stderr}")
    return output_path
