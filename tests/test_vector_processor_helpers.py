from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker" / "services"))

from vector_processor import build_postgis_table_name, detect_vector_type


def test_detect_vector_type_by_extension() -> None:
    assert detect_vector_type("layer.zip") == "shapefile"
    assert detect_vector_type("layer.kml") == "kml"
    assert detect_vector_type("layer.geojson") == "geojson"
    assert detect_vector_type("layer.json") == "geojson"
    assert detect_vector_type("layer.tif") is None


def test_build_postgis_table_name() -> None:
    table_name = build_postgis_table_name("91a5ccf0-c2cd-4bc4-99f4-e07e35287313")
    assert table_name.startswith("layer_")
    assert "-" not in table_name
