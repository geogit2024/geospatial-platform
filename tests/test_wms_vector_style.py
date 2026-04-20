from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers.services import _vector_default_style_name


def test_vector_default_style_polygon_like() -> None:
    assert _vector_default_style_name("POLYGON") == "polygon"
    assert _vector_default_style_name("MULTIPOLYGON") == "polygon"
    assert _vector_default_style_name("GEOMETRY") == "polygon"
    assert _vector_default_style_name(None) == "polygon"


def test_vector_default_style_line_like() -> None:
    assert _vector_default_style_name("LINESTRING") == "line"
    assert _vector_default_style_name("MULTILINESTRING") == "line"


def test_vector_default_style_point_like() -> None:
    assert _vector_default_style_name("POINT") == "point"
    assert _vector_default_style_name("MULTIPOINT") == "point"
