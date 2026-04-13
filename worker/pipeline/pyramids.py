import subprocess


OVERVIEW_LEVELS = [2, 4, 8, 16, 32, 64, 128]


def build_overviews(file_path: str, resampling: str = "average") -> str:
    """Build external overviews (pyramids) on a GeoTIFF file."""
    levels = [str(l) for l in OVERVIEW_LEVELS]
    cmd = ["gdaladdo", "-r", resampling, file_path] + levels
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdaladdo failed: {result.stderr}")
    return file_path
