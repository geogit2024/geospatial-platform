import importlib.util
import sys
import types
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
module_path = project_root / "worker" / "services" / "vector_processor.py"

config_stub = types.ModuleType("config")
config_stub.get_settings = lambda: types.SimpleNamespace(
    database_url="postgresql+asyncpg://geo:geo@postgres:5432/geodb",
    postgis_schema="public",
    vector_simplify_tolerance=0.0,
    vector_simplify_min_features=5000,
)
existing_config = sys.modules.get("config")
sys.modules["config"] = config_stub

spec = importlib.util.spec_from_file_location("vector_processor_under_test", module_path)
assert spec is not None and spec.loader is not None
vector_processor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vector_processor)

if existing_config is not None:
    sys.modules["config"] = existing_config
else:
    sys.modules.pop("config", None)

build_postgis_table_name = vector_processor.build_postgis_table_name
detect_vector_type = vector_processor.detect_vector_type
_to_sync_database_url = vector_processor._to_sync_database_url


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


def test_sync_database_url_converts_ssl_to_sslmode_for_psycopg2() -> None:
    source = "postgresql+asyncpg://geo:pass@db.example:5432/geodb?ssl=require"
    converted = _to_sync_database_url(source)

    assert converted.startswith("postgresql+psycopg2://")
    assert "sslmode=require" in converted
    assert "ssl=require" not in converted


def test_sync_database_url_keeps_explicit_sslmode_and_drops_ssl_duplicate() -> None:
    source = (
        "postgresql://geo:pass@db.example:5432/geodb"
        "?ssl=require&sslmode=verify-full&application_name=worker"
    )
    converted = _to_sync_database_url(source)

    assert converted.startswith("postgresql+psycopg2://")
    assert "sslmode=verify-full" in converted
    assert "application_name=worker" in converted
    assert "ssl=require" not in converted
