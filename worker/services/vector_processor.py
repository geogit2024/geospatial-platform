import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import get_settings

settings = get_settings()
log = logging.getLogger("worker.vector_processor")

_VECTOR_TYPES_BY_EXTENSION = {
    ".zip": "shapefile",
    ".kml": "kml",
    ".geojson": "geojson",
    ".json": "geojson",
}
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_INVALID_IDENTIFIER_CHARS_RE = re.compile(r"[^a-z0-9_]+")
_REQUIRED_SHAPEFILE_PARTS = (".shp", ".shx", ".dbf")


def _normalize_psycopg2_query_options(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if not parsed.query:
        return database_url

    params = parse_qsl(parsed.query, keep_blank_values=True)
    has_sslmode = any(key == "sslmode" for key, _ in params)
    normalized: list[tuple[str, str]] = []
    for key, value in params:
        if key == "ssl":
            if has_sslmode:
                continue
            normalized.append(("sslmode", value))
            continue
        normalized.append((key, value))

    updated_query = urlencode(normalized, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, updated_query, parsed.fragment))


def _require_geopandas():
    try:
        import geopandas as gpd  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Geopandas is required for vector uploads but is not available in the worker image"
        ) from exc
    return gpd


def _to_sync_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://") and "+psycopg2" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    if database_url.startswith("postgresql+psycopg2://"):
        return _normalize_psycopg2_query_options(database_url)
    return database_url


def _sync_engine() -> Engine:
    return create_engine(_to_sync_database_url(settings.database_url), pool_pre_ping=True, future=True)


def _normalize_identifier(name: str, used: set[str], *, default_prefix: str = "field") -> str:
    normalized = _INVALID_IDENTIFIER_CHARS_RE.sub("_", (name or "").strip().lower()).strip("_")
    if not normalized:
        normalized = default_prefix
    if normalized[0].isdigit():
        normalized = f"{default_prefix}_{normalized}"
    normalized = normalized[:55]

    candidate = normalized
    suffix = 1
    while candidate in used:
        suffix_text = f"_{suffix}"
        candidate = f"{normalized[:55 - len(suffix_text)]}{suffix_text}"
        suffix += 1

    used.add(candidate)
    return candidate


def _is_supported_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _sanitize_non_geometry_columns(gdf):
    used_names: set[str] = {"geom"}
    rename_map: dict[str, str] = {}

    for column in list(gdf.columns):
        if column == gdf.geometry.name:
            continue

        normalized = _normalize_identifier(str(column), used_names)
        rename_map[column] = normalized

    if rename_map:
        gdf = gdf.rename(columns=rename_map)

    for column in list(gdf.columns):
        if column == gdf.geometry.name:
            continue

        series = gdf[column]
        needs_string_cast = bool(series.map(lambda value: not _is_supported_scalar(value)).any())
        if needs_string_cast:
            gdf[column] = series.map(lambda value: None if value is None else str(value))

    return gdf


def _fix_invalid_geometries(gdf):
    polygon_like = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    if bool(polygon_like.any()):
        gdf.loc[polygon_like, gdf.geometry.name] = gdf.loc[polygon_like, gdf.geometry.name].buffer(0)
    return gdf


def _maybe_simplify(gdf):
    tolerance = float(settings.vector_simplify_tolerance or 0.0)
    min_features = int(settings.vector_simplify_min_features or 0)
    if tolerance <= 0 or len(gdf.index) < max(min_features, 1):
        return gdf

    log.info("Applying vector simplification: tolerance=%s features=%s", tolerance, len(gdf.index))
    gdf[gdf.geometry.name] = gdf.geometry.simplify(tolerance=tolerance, preserve_topology=True)
    return gdf


def _validate_table_name(table_name: str) -> None:
    if not _SAFE_IDENTIFIER_RE.match(table_name):
        raise ValueError(f"Invalid PostGIS table name: {table_name!r}")


def detect_vector_type(filename: str) -> str | None:
    ext = Path(filename or "").suffix.lower()
    return _VECTOR_TYPES_BY_EXTENSION.get(ext)


def build_postgis_table_name(image_id: str) -> str:
    token = re.sub(r"[^a-z0-9]", "", (image_id or "").lower())
    token = token[:20] if token else "unknown"
    table_name = f"layer_{token}"
    _validate_table_name(table_name)
    return table_name


def _find_shapefile_root(unzipped_dir: Path) -> Path:
    candidates = sorted(unzipped_dir.rglob("*.shp"))
    if not candidates:
        raise RuntimeError("ZIP does not contain any .shp file")

    for shp_path in candidates:
        missing_parts = [
            ext for ext in _REQUIRED_SHAPEFILE_PARTS if not shp_path.with_suffix(ext).exists()
        ]
        if not missing_parts:
            return shp_path

    missing = ", ".join(_REQUIRED_SHAPEFILE_PARTS)
    raise RuntimeError(f"Shapefile is incomplete in ZIP. Required sidecars: {missing}")


def process_shapefile(file_path: str):
    gpd = _require_geopandas()
    if not zipfile.is_zipfile(file_path):
        raise RuntimeError("Shapefile upload must be a valid .zip")

    extract_dir = Path(tempfile.mkdtemp(prefix="vector_shp_"))
    try:
        with zipfile.ZipFile(file_path, "r") as archive:
            archive.extractall(extract_dir)

        shp_path = _find_shapefile_root(extract_dir)
        return gpd.read_file(shp_path)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def process_kml(file_path: str):
    gpd = _require_geopandas()
    return gpd.read_file(file_path, driver="KML")


def process_geojson(file_path: str):
    gpd = _require_geopandas()
    return gpd.read_file(file_path)


def padronizar_gdf(gdf):
    if gdf is None or gdf.empty:
        raise RuntimeError("Uploaded vector has no features")
    if gdf.geometry is None:
        raise RuntimeError("Uploaded vector has no geometry column")

    gdf = gdf.copy()
    gdf = gdf[gdf.geometry.notnull()]
    gdf = gdf[~gdf.geometry.is_empty]

    if gdf.empty:
        raise RuntimeError("Uploaded vector has only empty geometries")

    if gdf.crs is None:
        log.warning("Vector has no CRS metadata. Assuming EPSG:4326.")
        gdf = gdf.set_crs(epsg=4326, allow_override=True)
    elif str(gdf.crs).upper() not in ("EPSG:4326", "WGS84"):
        gdf = gdf.to_crs(epsg=4326)

    gdf = _fix_invalid_geometries(gdf)
    gdf = gdf[gdf.geometry.notnull()]
    gdf = gdf[~gdf.geometry.is_empty]
    gdf = gdf[gdf.geometry.is_valid]

    if gdf.empty:
        raise RuntimeError("All geometries became invalid after normalization")

    gdf = _sanitize_non_geometry_columns(gdf)
    gdf = _maybe_simplify(gdf)

    if gdf.geometry.name != "geom":
        gdf = gdf.rename_geometry("geom")
    gdf = gdf.set_geometry("geom")

    return gdf


def salvar_postgis(gdf, table_name: str) -> None:
    _validate_table_name(table_name)
    schema = settings.postgis_schema or "public"
    _validate_table_name(schema)
    engine = _sync_engine()
    index_name = f"idx_{table_name[:48]}_geom"
    _validate_table_name(index_name)

    try:
        gdf.to_postgis(
            name=table_name,
            con=engine,
            schema=schema,
            if_exists="replace",
            index=False,
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                    f'ON "{schema}"."{table_name}" USING GIST ("geom")'
                )
            )
    finally:
        engine.dispose()


def process_vector_file(file_path: str, vector_type: str, table_name: str) -> dict[str, Any]:
    if vector_type == "shapefile":
        gdf = process_shapefile(file_path)
    elif vector_type == "kml":
        gdf = process_kml(file_path)
    elif vector_type == "geojson":
        gdf = process_geojson(file_path)
    else:
        raise RuntimeError(f"Unsupported vector type: {vector_type}")

    gdf = padronizar_gdf(gdf)
    salvar_postgis(gdf, table_name)

    minx, miny, maxx, maxy = gdf.total_bounds.tolist()
    geometry_types = sorted({str(item).upper() for item in gdf.geom_type.dropna().tolist()})
    geometry_type = geometry_types[0] if len(geometry_types) == 1 else "GEOMETRY"

    return {
        "table_name": table_name,
        "schema": settings.postgis_schema or "public",
        "crs": "EPSG:4326",
        "bbox_wgs84": {
            "minx": float(minx),
            "miny": float(miny),
            "maxx": float(maxx),
            "maxy": float(maxy),
        },
        "geometry_type": geometry_type,
        "feature_count": int(len(gdf.index)),
    }
