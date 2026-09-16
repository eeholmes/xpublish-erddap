"""End-to-end tests of the ERDDAP API surface via FastAPI's TestClient."""

import io

import pandas as pd
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin
from xpublish_erddap.catalog import check_axes


@pytest.fixture(scope="session")
def client(grid_dataset):
    rest = xpublish.Rest(
        {"testgrid": grid_dataset},
        plugins={"erddap": ErddapPlugin(metadata={"infoUrl": "https://example.org"})},
    )
    return TestClient(rest.app)


def test_version(client):
    assert "ERDDAP_version" in client.get("/erddap/version").text


def test_catalog_splits_by_dimension_signature(client):
    """ERDDAP requires one hypercube per dataset, so 'depth' vars split out."""
    body = client.get("/erddap/griddap/index.csv").text
    assert "testgrid" in body
    assert "testgrid_depth" in body


def test_dds_uses_erddap_uppercase_keywords(client):
    """erddapy parses the DDS with split('GRID'); the casing is load-bearing."""
    body = client.get("/erddap/griddap/testgrid.dds").text
    assert "GRID {" in body
    assert "ARRAY:" in body
    assert "MAPS:" in body
    assert "Grid {" not in body


def test_das_lists_globals_alphabetically(client):
    """rerddap reads time_coverage_end/_start positionally from this order."""
    body = client.get("/erddap/griddap/testgrid.das").text
    assert body.index("time_coverage_end") < body.index("time_coverage_start")


def test_info_has_erddap_column_names(client):
    body = client.get("/erddap/info/testgrid/index.csv").text
    header = body.splitlines()[0]
    assert header == "Row Type,Variable Name,Attribute Name,Data Type,Value"


def test_info_json_content_type_is_exact(client):
    """rerddap asserts on this exact string, space included (or rather, not)."""
    resp = client.get("/erddap/info/testgrid/index.json")
    assert resp.headers["content-type"] == "application/json;charset=UTF-8"


def test_tabledap_index_is_empty_not_404(client):
    """rerddap calls this to classify a datasetID; a 404 breaks info()."""
    resp = client.get("/erddap/tabledap/index.json")
    assert resp.status_code == 200
    assert resp.json()["table"]["rows"] == []


def test_ioos_category_is_filled_in(client):
    body = client.get("/erddap/info/testgrid/index.csv").text
    assert "ioos_category" in body
    assert "Temperature" in body


def test_coordinate_value_subsetting(client):
    url = (
        "/erddap/griddap/testgrid.csvp"
        "?tos[(2020-01-02T00:00:00Z):1:(2020-01-03T00:00:00Z)]"
        "[(42.5):1:(47.5)][(232.0):1:(236.0)]"
    )
    df = pd.read_csv(io.StringIO(client.get(url).text))
    assert len(df) == 2 * 3 * 2
    assert list(df.columns) == [
        "time (UTC)",
        "lat (degrees_north)",
        "lon (degrees_east)",
        "tos (degC)",
    ]


def test_index_subsetting_matches_coordinate_subsetting(client):
    a = client.get("/erddap/griddap/testgrid.csv?tos[0:1:1][0:1:1][0:1:1]").text
    b = client.get(
        "/erddap/griddap/testgrid.csv"
        "?tos[(2020-01-01T00:00:00Z):1:(2020-01-02T00:00:00Z)]"
        "[(40.0):1:(42.5)][(230.0):1:(233.333)]",
    ).text
    assert a == b


def test_stride_is_honoured(client):
    df = pd.read_csv(
        io.StringIO(client.get("/erddap/griddap/testgrid.csvp?tos[0:2:5][0][0]").text),
    )
    assert len(df) == 3


def test_netcdf_roundtrip(client):
    resp = client.get("/erddap/griddap/testgrid.nc?tos[0:1:2][0:1:2][0:1:1]")
    assert resp.headers["content-type"] == "application/x-netcdf"
    assert resp.content[:3] == b"CDF", "ERDDAP serves netCDF-3 classic for .nc"
    ds = xr.open_dataset(io.BytesIO(resp.content), engine="scipy")
    assert ds.tos.shape == (3, 3, 2)
    assert ds.time.dtype.kind == "M"


def test_json_response_shape(client):
    payload = client.get("/erddap/griddap/testgrid.json?tos[0][0][0]").json()
    assert set(payload["table"]) == {
        "columnNames",
        "columnTypes",
        "columnUnits",
        "rows",
    }
    assert payload["table"]["columnNames"] == ["time", "lat", "lon", "tos"]


def test_search_finds_and_filters(client):
    assert client.get("/erddap/search/index.csv?searchFor=testgrid").status_code == 200
    assert client.get("/erddap/search/index.csv?searchFor=zzznope").status_code == 404


def test_unknown_dataset_is_404(client):
    assert client.get("/erddap/griddap/nope.csv").status_code == 404


def test_unsupported_filetype_is_400(client):
    resp = client.get("/erddap/griddap/testgrid.mat")
    assert resp.status_code == 400
    assert "unsupported fileType" in resp.text


def test_bad_constraint_is_400(client):
    resp = client.get("/erddap/griddap/testgrid.csv?tos[0][0]")
    assert resp.status_code == 400


def test_non_monotonic_axis_is_refused_like_erddap(grid_dataset):
    """ERDDAP refuses non-monotonic axes; serving them corrupts index ranges."""
    broken = grid_dataset.copy()
    times = broken.time.values.copy()
    times[-1] = times[0]  # duplicate, breaking monotonicity
    broken = broken.assign_coords(time=times)

    rest = xpublish.Rest({"broken": broken}, plugins={"erddap": ErddapPlugin()})
    body = TestClient(rest.app).get("/erddap/griddap/index.csv").text
    assert "broken" not in body

    lax = xpublish.Rest(
        {"broken2": broken},
        plugins={"erddap": ErddapPlugin(strict_axes=False)},
    )
    body = TestClient(lax.app).get("/erddap/griddap/index.csv").text
    assert "broken2" in body


def test_check_axes_reports_the_break():
    t = pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-02"])
    ds = xr.Dataset({"v": ("time", [1.0, 2.0, 3.0])}, coords={"time": t})
    problems = check_axes(ds, ("time",))
    assert len(problems) == 1
    assert problems[0].axis == "time"
    assert "not strictly monotonic" in problems[0].reason
    assert "index 1" in problems[0].reason


def test_ncml_matches_what_erddapy_parses(client):
    """erddapy >=3.2 discovers a griddap dataset from .ncml alone."""
    import xml.etree.ElementTree as ET

    from xpublish_erddap.formats import NCML_NS

    resp = client.get("/erddap/griddap/testgrid.ncml")
    assert resp.status_code == 200
    root = ET.fromstring(resp.text)

    dims = [d.attrib["name"] for d in root.findall(f"{{{NCML_NS}}}dimension")]
    variables = [v.attrib["name"] for v in root.findall(f"{{{NCML_NS}}}variable")]
    assert dims == ["time", "lat", "lon"]
    # erddapy derives data variables by subtracting dimension names
    assert set(variables) - set(dims) == {"tos", "sos"}

    # it raises if any dimension lacks a space-separated actual_range
    ns = {"nc": NCML_NS}
    for dim in dims:
        el = root.find(
            f'nc:variable[@name="{dim}"]/nc:attribute[@name="actual_range"]',
            namespaces=ns,
        )
        assert el is not None, f"{dim} has no actual_range"
        low, high = el.attrib["value"].split()
        assert float(low) <= float(high)
