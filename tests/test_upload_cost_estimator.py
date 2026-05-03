from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from services.upload_cost_estimator import (  # noqa: E402
    build_quick_analysis,
    calculate_cost_estimate,
    classify_asset_type,
)


def test_quick_analysis_identifies_raster() -> None:
    analysis = build_quick_analysis(
        filename="scene.tif",
        size_bytes=1_073_741_824,
        content_type="image/tiff",
    )
    assert analysis["asset_type"] == "raster"
    assert analysis["extension"] == ".tif"
    assert analysis["size_gb"] == 1.0


def test_quick_analysis_identifies_vector() -> None:
    assert classify_asset_type(extension=".geojson", content_type="application/json") == "vector"


def test_cost_estimate_calculation_returns_expected_structure() -> None:
    analysis = {
        "asset_type": "raster",
        "size_gb": 2.0,
        "complexity_factor": 1.0,
    }
    pricing = {
        "cost_per_gb_month": 0.2,
        "cost_per_process": 0.1,
        "cost_per_download": 0.01,
        "currency": "BRL",
    }
    assumptions = {
        "expected_monthly_downloads": 100,
        "avg_download_size_ratio": 0.5,
        "processed_size_ratio_raster": 0.6,
        "processed_size_ratio_vector": 0.3,
        "processing_base_units": 1.0,
        "processing_units_per_gb_raster": 2.0,
        "processing_units_per_gb_vector": 1.0,
        "uncertainty_min_factor": 0.7,
        "uncertainty_max_factor": 1.4,
    }

    estimate = calculate_cost_estimate(
        analysis=analysis,
        pricing=pricing,
        assumptions=assumptions,
    )

    assert estimate["currency"] == "BRL"
    assert estimate["breakdown"]["processing_one_time"] > 0
    assert estimate["breakdown"]["storage_monthly"] > 0
    assert estimate["breakdown"]["publication_monthly"] == 1.0
    assert estimate["breakdown"]["first_month_range"]["maximum"] >= estimate["breakdown"]["first_month_total"]
