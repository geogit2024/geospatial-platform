from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from services.metrics_storage import (
    _build_usage_timeseries,
    bytes_to_gb,
    bytes_to_mb,
    calculate_growth_percent,
    normalize_file_type,
)


def test_normalize_file_type_geotiff_variants() -> None:
    assert normalize_file_type("tile_01.tif") == "geotiff"
    assert normalize_file_type("tile_02.TIFF") == "geotiff"
    assert normalize_file_type("tile_03.geotiff") == "geotiff"


def test_calculate_growth_percent_handles_zero_base() -> None:
    assert calculate_growth_percent(0, 0) == 0.0
    assert calculate_growth_percent(1024, 0) == 100.0


def test_usage_timeseries_aggregates_and_accumulates() -> None:
    now = datetime.utcnow()
    image_stats = [
        {"created_at": now - timedelta(days=2), "size_bytes": 1024 * 1024 * 1024},
        {"created_at": now - timedelta(days=1), "size_bytes": 512 * 1024 * 1024},
    ]

    series = _build_usage_timeseries(image_stats, window_days=3)

    assert len(series) == 3
    assert series[0]["files_added"] == 1
    assert series[1]["files_added"] == 1
    assert series[2]["files_added"] == 0

    expected_total = bytes_to_gb((1024 + 512) * 1024 * 1024)
    assert round(series[-1]["total_gb"], 4) == round(expected_total, 4)


def test_unit_conversions() -> None:
    assert round(bytes_to_mb(1048576), 2) == 1.0
    assert round(bytes_to_gb(1073741824), 2) == 1.0
