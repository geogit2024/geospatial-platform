from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from services.processing_strategy import classify_processing_strategy


def test_geotiff_uses_raster_light_strategy() -> None:
    strategy = classify_processing_strategy(filename="area.geotiff", size_bytes=10_000)

    assert strategy.asset_kind == "raster"
    assert strategy.processing_strategy == "raster_light"
    assert strategy.worker_type == "raster"
    assert strategy.requires_gdal is True
    assert strategy.requires_postgis is False
    assert strategy.requires_geoserver is True


def test_jp2_uses_raster_heavy_strategy() -> None:
    strategy = classify_processing_strategy(filename="ortho.jp2", size_bytes=10_000)

    assert strategy.asset_kind == "raster"
    assert strategy.processing_strategy == "raster_heavy"
    assert strategy.worker_type == "raster-heavy"


def test_zip_uses_vector_heavy_strategy() -> None:
    strategy = classify_processing_strategy(filename="layer.zip", size_bytes=10_000)

    assert strategy.asset_kind == "vector"
    assert strategy.processing_strategy == "zip_vector"
    assert strategy.requires_postgis is True


def test_small_geojson_uses_vector_light_strategy() -> None:
    strategy = classify_processing_strategy(filename="layer.geojson", size_bytes=2 * 1024 * 1024)

    assert strategy.asset_kind == "vector"
    assert strategy.processing_strategy == "vector_light"
    assert strategy.processing_queue == "processing:vector-light"


def test_large_geojson_uses_vector_heavy_strategy() -> None:
    strategy = classify_processing_strategy(filename="layer.geojson", size_bytes=30 * 1024 * 1024)

    assert strategy.asset_kind == "vector"
    assert strategy.processing_strategy == "vector_heavy"
    assert strategy.processing_queue == "processing:vector-heavy"
