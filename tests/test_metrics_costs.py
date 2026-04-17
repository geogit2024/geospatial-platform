from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from services.metrics_costs import (
    calculate_download_cost,
    calculate_processing_cost,
    calculate_projection_30_days,
    calculate_storage_cost,
    simulate_costs,
)


def test_cost_formulas_basic() -> None:
    assert round(calculate_storage_cost(100, 0.15), 2) == 15.0
    assert round(calculate_processing_cost(200, 0.05), 2) == 10.0
    assert round(calculate_download_cost(500, 0.01), 2) == 5.0


def test_projection_uses_daily_average() -> None:
    series = [
        {"date": "2026-04-01", "value": 3.0},
        {"date": "2026-04-02", "value": 5.0},
        {"date": "2026-04-03", "value": 4.0},
    ]
    # average 4.0 * 30
    assert round(calculate_projection_30_days(series, fallback_total=0.0), 2) == 120.0


def test_projection_fallback_when_empty() -> None:
    assert calculate_projection_30_days([], fallback_total=77.7) == 77.7


def test_simulate_costs_output() -> None:
    result = simulate_costs(
        current_total=100.0,
        cost_per_gb=0.15,
        cost_per_process=0.05,
        cost_per_download=0.01,
        extra_gb=10.0,
        extra_processes=20,
        extra_downloads=50,
    )

    assert result["extra_storage_cost"] == 1.5
    assert result["extra_processing_cost"] == 1.0
    assert result["extra_download_cost"] == 0.5
    assert result["extra_total"] == 3.0
    assert result["new_estimated_total"] == 103.0
