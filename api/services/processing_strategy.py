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
        return ProcessingStrategy(
            asset_kind="raster",
            source_format=ext.lstrip("."),
            processing_strategy="raster_light",
            worker_type="raster",
            processing_queue="processing:raster-light",
            requires_gdal=True,
            requires_postgis=False,
            requires_geoserver=True,
        )

    if ext in _RASTER_HEAVY_EXTENSIONS:
        return ProcessingStrategy(
            asset_kind="raster",
            source_format=ext.lstrip("."),
            processing_strategy="raster_heavy",
            worker_type="raster-heavy",
            processing_queue="processing:raster-heavy",
            requires_gdal=True,
            requires_postgis=False,
            requires_geoserver=True,
        )

    if ext in _JPEG_EXTENSIONS:
        return ProcessingStrategy(
            asset_kind="raster",
            source_format=ext.lstrip("."),
            processing_strategy="jpeg_georeferenced",
            worker_type="raster",
            processing_queue="processing:raster-light",
            requires_gdal=True,
            requires_postgis=False,
            requires_geoserver=True,
        )

    if ext in _VECTOR_ARCHIVE_EXTENSIONS:
        return ProcessingStrategy(
            asset_kind="vector",
            source_format=ext.lstrip("."),
            processing_strategy="zip_vector",
            worker_type="vector-heavy",
            processing_queue="processing:vector-heavy",
            requires_gdal=False,
            requires_postgis=True,
            requires_geoserver=True,
        )

    if ext in _VECTOR_LIGHT_EXTENSIONS:
        strategy = "vector_light" if size_mb <= 20 else "vector_heavy"
        return ProcessingStrategy(
            asset_kind="vector",
            source_format=ext.lstrip("."),
            processing_strategy=strategy,
            worker_type="vector" if strategy == "vector_light" else "vector-heavy",
            processing_queue=f"processing:{strategy.replace('_', '-')}",
            requires_gdal=False,
            requires_postgis=True,
            requires_geoserver=True,
        )

    normalized_type = (content_type or "").strip().lower()
    if "geo+json" in normalized_type:
        return ProcessingStrategy(
            asset_kind="vector",
            source_format=ext.lstrip(".") or "geojson",
            processing_strategy="vector_light",
            worker_type="vector",
            processing_queue="processing:vector-light",
            requires_gdal=False,
            requires_postgis=True,
            requires_geoserver=True,
        )

    return ProcessingStrategy(
        asset_kind="raster",
        source_format=ext.lstrip(".") or "unknown",
        processing_strategy="raster_heavy",
        worker_type="raster-heavy",
        processing_queue="processing:raster-heavy",
        requires_gdal=True,
        requires_postgis=False,
        requires_geoserver=True,
    )
