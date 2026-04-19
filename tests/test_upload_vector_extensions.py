from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers.upload import ALLOWED_EXTENSIONS, _CONTENT_TYPE_MAP


def test_upload_router_accepts_vector_extensions() -> None:
    assert ".zip" in ALLOWED_EXTENSIONS
    assert ".kml" in ALLOWED_EXTENSIONS
    assert ".geojson" in ALLOWED_EXTENSIONS
    assert ".json" in ALLOWED_EXTENSIONS


def test_upload_router_content_type_mapping_for_vectors() -> None:
    assert _CONTENT_TYPE_MAP[".zip"] == "application/zip"
    assert _CONTENT_TYPE_MAP[".kml"] == "application/vnd.google-earth.kml+xml"
    assert _CONTENT_TYPE_MAP[".geojson"] == "application/geo+json"
    assert _CONTENT_TYPE_MAP[".json"] == "application/geo+json"


def test_upload_router_does_not_allow_ecw_without_driver() -> None:
    assert ".ecw" not in ALLOWED_EXTENSIONS
    assert ".ecw" not in _CONTENT_TYPE_MAP
