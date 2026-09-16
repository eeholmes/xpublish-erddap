"""End-to-end tests of the ERDDAP API surface via FastAPI's TestClient."""

import io

import numpy as np
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


def test_dods_is_planned_not_advertised(client):
    """Issue #2: .dods answers 501 with a pointer, and no error lists it."""
    resp = client.get("/erddap/griddap/testgrid.dods")
    assert resp.status_code == 501
    assert "issues/2" in resp.json()["detail"]
    other = client.get("/erddap/griddap/testgrid.htmlTable")
    assert other.status_code == 400
    assert "dods" not in other.json()["detail"]


def test_float32_values_print_as_written(client):
    """ERDDAP writes a float32 0.1 as 0.1, not 0.10000000149011612."""
    rest = xpublish.Rest(
        {
            "f32": xr.Dataset(
                {"v": ("x", np.array([0.1, 0.2], dtype="float32"))},
                coords={"x": np.array([0.1, 0.2], dtype="float32")},
            ),
        },
        plugins={"erddap": ErddapPlugin()},
    )
    c = TestClient(rest.app)
    assert c.get("/erddap/griddap/f32.csv0?v[0:1:1]").text == "0.1,0.1\n0.2,0.2\n"
    assert "Float32 actual_range 0.1, 0.2;" in c.get("/erddap/griddap/f32.das").text


def test_globals_sort_ignoring_case_and_hide_xpublish_id(client):
    body = client.get("/erddap/info/testgrid/index.csv").text
    names = [
        line.split(",")[2]
        for line in body.splitlines()
        if line.startswith("attribute,NC_GLOBAL,")
    ]
    assert names == sorted(names, key=str.lower)
    assert "_xpublish_id" not in names


def test_axis_only_columns_sit_side_by_side(client):
    """ERDDAP pads shorter axis columns with blanks, no cartesian product."""
    body = client.get("/erddap/griddap/testgrid.csv0?time[(last)],lat[0:1:2]").text
    assert body == "2020-01-06T00:00:00Z,40.0\n,42.5\n,45.0\n"


def test_fill_values_from_encoding_are_listed(tmp_path):
    """Zarr/netCDF stores keep _FillValue in .encoding; clients need it."""
    ds = xr.Dataset(
        {"v": ("x", np.array([1.0, -999.0], dtype="float32"))},
        coords={"x": [0.0, 1.0]},
    )
    ds.v.encoding.update({"_FillValue": -999.0, "missing_value": -999.0})
    path = tmp_path / "fill.nc"
    ds.to_netcdf(path)
    opened = xr.open_dataset(path)
    assert "_FillValue" not in opened.v.attrs

    c = TestClient(
        xpublish.Rest({"fill": opened}, plugins={"erddap": ErddapPlugin()}).app,
    )
    das = c.get("/erddap/griddap/fill.das").text
    assert "Float32 _FillValue -999.0;" in das
    assert "Float32 missing_value -999.0;" in das
    info = c.get("/erddap/info/fill/index.csv").text
    assert "attribute,v,_FillValue," in info
    nc = xr.open_dataset(
        io.BytesIO(c.get("/erddap/griddap/fill.nc?v[0:1:1]").content),
        decode_cf=False,
    )
    assert nc.v.attrs["_FillValue"] == -999.0
    assert nc.v.attrs["missing_value"] == -999.0


def test_subset_netcdf_describes_the_subset(client):
    """Like ERDDAP, a .nc download's coverage metadata is the subset's."""
    resp = client.get("/erddap/griddap/testgrid.nc?tos[1:1:2][1:1:2][0:1:1]")
    ds = xr.open_dataset(io.BytesIO(resp.content), decode_cf=False)
    assert ds.attrs["time_coverage_start"] == "2020-01-02T00:00:00Z"
    assert ds.attrs["time_coverage_end"] == "2020-01-03T00:00:00Z"
    assert ds.attrs["geospatial_lat_min"] == 42.5
    assert ds.attrs["Northernmost_Northing"] == 45.0
    assert ds.attrs["Westernmost_Easting"] == 230.0
    assert list(ds.lat.attrs["actual_range"]) == [42.5, 45.0]
    assert "_FillValue" not in ds.lat.attrs
    assert ds.time.attrs["units"] == "seconds since 1970-01-01T00:00:00Z"
    assert "calendar" not in ds.time.attrs
    assert list(ds.time.attrs["actual_range"]) == [1577923200.0, 1578009600.0]


def test_full_dataset_gets_bounding_box_globals(client):
    """ERDDAP adds *most_* globals even when the source has none."""
    das = client.get("/erddap/griddap/testgrid.das").text
    assert "Float64 Northernmost_Northing 50.0;" in das
    assert "Float64 Easternmost_Easting 240.0;" in das


def test_axis_only_netcdf_holds_only_the_axes(client):
    """Copilot review: ?time[(last)] must not ship the whole data grid."""
    resp = client.get("/erddap/griddap/testgrid.nc?time[(last)]")
    ds = xr.open_dataset(io.BytesIO(resp.content), decode_cf=False)
    assert list(ds.variables) == ["time"]
    assert ds.sizes == {"time": 1}
    assert not any(k.startswith("geospatial_") for k in ds.attrs)
    assert ds.attrs["time_coverage_start"] == "2020-01-06T00:00:00Z"


def test_unknown_table_filetypes_are_404(client):
    """ERDDAP answers 404 for an unknown fileType on its table routes."""
    for path in (
        "/erddap/info/testgrid/index.htmlTable",
        "/erddap/info/index.foo",
        "/erddap/search/index.foo?searchFor=test",
        "/erddap/tabledap/index.foo",
    ):
        assert client.get(path).status_code == 404, path


def test_missing_filetype_message_lists_every_type(client):
    detail = client.get("/erddap/griddap/testgrid").json()["detail"]
    assert "ncml" in detail
    assert "dods" not in detail


def test_integer_variable_with_nan_fill_still_serves_metadata():
    """Copilot review: a NaN fill cannot be cast to an integer dtype."""
    ds = xr.Dataset({"n": ("x", np.array([1, 2], dtype="int16"))}, coords={"x": [0, 1]})
    ds.n.encoding.update({"_FillValue": np.nan, "scale_factor": 0.1})
    c = TestClient(xpublish.Rest({"ints": ds}, plugins={"erddap": ErddapPlugin()}).app)
    das = c.get("/erddap/griddap/ints.das")
    assert das.status_code == 200
    assert "_FillValue" not in das.text
