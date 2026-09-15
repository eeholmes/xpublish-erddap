"""End-to-end tests of the ERDDAP API surface via FastAPI's TestClient."""

import io

import pandas as pd
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin


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
        "time (UTC)", "lat (degrees_north)", "lon (degrees_east)", "tos (degC)",
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
    ds = xr.open_dataset(io.BytesIO(resp.content))
    assert ds.tos.shape == (3, 3, 2)
    assert ds.time.dtype.kind == "M"


def test_json_response_shape(client):
    payload = client.get("/erddap/griddap/testgrid.json?tos[0][0][0]").json()
    assert set(payload["table"]) == {
        "columnNames", "columnTypes", "columnUnits", "rows",
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
