from __future__ import annotations

from dataclasses import asdict, dataclass


_RASTER_LIGHT_EXTENSIONS = {".tif", ".tiff", ".geotiff"}
_RASTER_HEAVY_EXTENSIONS = {".jp2", ".img"}
_JPEG_EXTENSIONS = {".jpg", ".jpeg"}
_VECTOR_ARCHIVE_EXTENSIONS = {".zip"}
_VECTOR_LIGHT_EXTENSIONS = {".kml", ".geojson", ".json"}


@dataclass(frozen=True)
class ProcessingStrategy:
    asset_kind: str
    source_format: str
    processing_strategy: str
    worker_type: str
    processing_queue: str
    requires_gdal: bool
    requires_postgis: bool
    requires_geoserver: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].strip().lower()


def classify_processing_strategy(
    *,
    filename: str,
    size_bytes: int | None = None,
    content_type: str = "",
) -> ProcessingStrategy:
    ext = normalize_extension(filename)
    size_mb = max(float(size_bytes or 0), 0.0) / (1024.0 * 1024.0)

    if ext in _RASTER_LIGHT_EXTENSIONS:
        return ProcessingStrategy("raster", ext.lstrip("."), "raster_light", "raster", "processing:raster-light", True, False, True)
    if ext in _RASTER_HEAVY_EXTENSIONS:
        return ProcessingStrategy("raster", ext.lstrip("."), "raster_heavy", "raster-heavy", "processing:raster-heavy", True, False, True)
    if ext in _JPEG_EXTENSIONS:
        return ProcessingStrategy("raster", ext.lstrip("."), "jpeg_georeferenced", "raster", "processing:raster-light", True, False, True)
    if ext in _VECTOR_ARCHIVE_EXTENSIONS:
        return ProcessingStrategy("vector", ext.lstrip("."), "zip_vector", "vector-heavy", "processing:vector-heavy", False, True, True)
    if ext in _VECTOR_LIGHT_EXTENSIONS:
        strategy = "vector_light" if size_mb <= 20 else "vector_heavy"
        return ProcessingStrategy(
            "vector",
            ext.lstrip("."),
            strategy,
            "vector" if strategy == "vector_light" else "vector-heavy",
            f"processing:{strategy.replace('_', '-')}",
            False,
            True,
            True,
        )

    if "geo+json" in (content_type or "").strip().lower():
        return ProcessingStrategy("vector", ext.lstrip(".") or "geojson", "vector_light", "vector", "processing:vector-light", False, True, True)

    return ProcessingStrategy("raster", ext.lstrip(".") or "unknown", "raster_heavy", "raster-heavy", "processing:raster-heavy", True, False, True)
