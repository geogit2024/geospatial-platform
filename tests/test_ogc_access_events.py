from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers.services import _build_ogc_event_type


def test_build_ogc_event_type_uses_fallback_request() -> None:
    assert _build_ogc_event_type("wms", None, fallback_request="GetCapabilities") == "wms_getcapabilities"


def test_build_ogc_event_type_sanitizes_and_limits_to_model_length() -> None:
    event_type = _build_ogc_event_type("WMTS", "Get-Tile?Layer=foo/bar", fallback_request="GetCapabilities")
    assert event_type.startswith("wmts_get_tile_layer_foo_bar")
    assert len(event_type) <= 32
