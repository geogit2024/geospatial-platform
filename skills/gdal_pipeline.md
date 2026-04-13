# Skill: GDAL Pipeline

## Purpose
Reusable GDAL processing pipeline for converting raw rasters to Cloud Optimized
GeoTIFF (COG) with overviews, ready for OGC publication.

## Pipeline Steps

```
Input (raw raster: GeoTIFF, ECW, JP2, etc.)
  → Step 1: Validate & inspect (gdalinfo)
  → Step 2: Reproject to target CRS (gdalwarp)
  → Step 3: Convert to COG (gdal_translate + COMPRESS=DEFLATE + TILED=YES)
  → Step 4: Build overviews / pyramids (gdaladdo)
  → Output: COG (.tif) ready for GeoServer
```

## Implementation Notes

### Step 1 — Validate
```python
from osgeo import gdal
ds = gdal.Open(path)
if ds is None:
    raise ValueError(f"Cannot open {path}")
info = gdal.Info(ds, format='json')
```

### Step 2 — Reproject
```bash
gdalwarp -t_srs EPSG:4326 -r bilinear -of GTiff input.tif reprojected.tif
```
- Use `-r bilinear` for continuous data (elevation, imagery)
- Use `-r near` for categorical data (land cover, classification)

### Step 3 — COG
```bash
gdal_translate \
  -of COG \
  -co COMPRESS=DEFLATE \
  -co PREDICTOR=2 \
  -co TILED=YES \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co COPY_SRC_OVERVIEWS=YES \
  reprojected.tif output_cog.tif
```

### Step 4 — Overviews
```bash
gdaladdo -r average output_cog.tif 2 4 8 16 32 64
```

## Python Wrapper Pattern
```python
import subprocess, tempfile, os
from pathlib import Path

def run_gdal_pipeline(input_path: str, output_path: str, target_crs: str = "EPSG:4326") -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        reprojected = os.path.join(tmpdir, "reprojected.tif")
        subprocess.run([
            "gdalwarp", "-t_srs", target_crs, "-r", "bilinear",
            "-of", "GTiff", input_path, reprojected
        ], check=True)
        subprocess.run([
            "gdaladdo", "-r", "average", reprojected, "2", "4", "8", "16", "32", "64"
        ], check=True)
        subprocess.run([
            "gdal_translate", "-of", "COG",
            "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=2",
            "-co", "TILED=YES", "-co", "BLOCKXSIZE=512", "-co", "BLOCKYSIZE=512",
            "-co", "COPY_SRC_OVERVIEWS=YES",
            reprojected, output_path
        ], check=True)
    return output_path
```

## Key Constraints
- Always work in a temp directory; never modify source files
- Overviews must be built BEFORE gdal_translate to COG with COPY_SRC_OVERVIEWS=YES
- GDAL env var `GDAL_CACHEMAX=512` recommended for large files
- For very large files (>1GB), add `-wo CUTLINE_ALL_TOUCHED=YES` and chunk processing
