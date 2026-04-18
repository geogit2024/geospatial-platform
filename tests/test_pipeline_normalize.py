from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))

import pipeline as gdal_pipeline


def test_normalize_retries_warp_when_raster_has_no_affine_or_gcps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gdal_pipeline,
        "_gdalinfo",
        lambda _path: {"coordinateSystem": {"wkt": 'PROJCRS["WGS 84",ID["EPSG",4326]]'}},
    )

    calls: list[tuple[list[str], str]] = []

    def fake_run(cmd: list[str], label: str, timeout: int = 600) -> None:
        del timeout
        calls.append((cmd, label))
        if label == "gdalwarp EPSG:3857":
            raise RuntimeError(
                "gdalwarp EPSG:3857 failed (exit 1): ERROR 1: "
                "Unable to compute a transformation between pixel/line and georeferenced coordinates. "
                "There is no affine transformation and no GCPs."
            )

    monkeypatch.setattr(gdal_pipeline, "_run", fake_run)

    gdal_pipeline.normalize_raster("input.jpg", "output.tif")

    labels = [label for _cmd, label in calls]
    assert "gdalwarp EPSG:3857" in labels
    assert "gdalwarp EPSG:3857 (NO_GEOTRANSFORM)" in labels

    fallback_cmd = next(cmd for cmd, label in calls if label == "gdalwarp EPSG:3857 (NO_GEOTRANSFORM)")
    assert "-to" in fallback_cmd
    assert "SRC_METHOD=NO_GEOTRANSFORM" in fallback_cmd


def test_normalize_does_not_mask_unrelated_gdalwarp_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gdal_pipeline,
        "_gdalinfo",
        lambda _path: {"coordinateSystem": {"wkt": 'PROJCRS["WGS 84",ID["EPSG",4326]]'}},
    )

    def fake_run(cmd: list[str], label: str, timeout: int = 600) -> None:
        del cmd, timeout
        if label == "gdalwarp EPSG:3857":
            raise RuntimeError("gdalwarp EPSG:3857 failed (exit 1): ERROR 6: cannot open dataset")

    monkeypatch.setattr(gdal_pipeline, "_run", fake_run)

    with pytest.raises(RuntimeError, match="cannot open dataset"):
        gdal_pipeline.normalize_raster("input.jpg", "output.tif")
