from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers.services import _filter_wms_capabilities_to_layer


def test_filter_wms_capabilities_keeps_parent_crs_for_arcgis_compatibility() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities xmlns="http://www.opengis.net/wms" version="1.3.0">
  <Capability>
    <Layer>
      <Title>root</Title>
      <CRS>EPSG:3857</CRS>
      <CRS>EPSG:4326</CRS>
      <BoundingBox CRS="EPSG:3857" minx="-10" miny="-10" maxx="10" maxy="10" />
      <Layer>
        <Name>target_layer</Name>
        <Title>Target</Title>
        <CRS>EPSG:4326</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>-1</westBoundLongitude>
          <eastBoundLongitude>1</eastBoundLongitude>
          <southBoundLatitude>-1</southBoundLatitude>
          <northBoundLatitude>1</northBoundLatitude>
        </EX_GeographicBoundingBox>
        <BoundingBox CRS="EPSG:4326" minx="-1" miny="-1" maxx="1" maxy="1" />
      </Layer>
      <Layer>
        <Name>other_layer</Name>
        <Title>Other</Title>
        <CRS>EPSG:4326</CRS>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

    filtered = _filter_wms_capabilities_to_layer(xml, "ws:target_layer")

    assert ">target_layer<" in filtered
    assert ">other_layer<" not in filtered

    # Parent CRS list must keep WebMercator support for ArcGIS basemap compatibility.
    assert ">EPSG:3857<" in filtered
    assert ">EPSG:4326<" in filtered

    # Parent extent should be derived from the selected target child.
    assert 'CRS="EPSG:4326" minx="-1" miny="-1" maxx="1" maxy="1"' in filtered
