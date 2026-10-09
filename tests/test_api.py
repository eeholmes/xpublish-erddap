"""End-to-end tests of the ERDDAP API surface via FastAPI's TestClient."""

import io
import xml.etree.ElementTree as ET
from urllib.parse import quote

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import xpublish
from error_body import message
from fastapi import FastAPI
from fastapi.testclient import TestClient
from xpublish import Dependencies
from xpublish.dependencies import get_dataset_ids, get_datatree

import xpublish_erddap.plugin as plugin_module
from xpublish_erddap import ErddapPlugin
from xpublish_erddap.catalog import check_axes
from xpublish_erddap.formats import NCML_NS


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


def test_each_format_reads_the_way_its_client_expects(client):
    """One smoke test per format for the clients that depend on its shape.

    Parity (``tests/parity``) checks these formats against real ERDDAPs; what
    is left here is which client breaks when one changes.
    """
    # erddapy parses the DDS with split("GRID"): the casing is load-bearing
    dds = client.get("/erddap/griddap/testgrid.dds").text
    assert "GRID {" in dds
    assert "ARRAY:" in dds
    assert "MAPS:" in dds
    assert "Grid {" not in dds

    # rerddap reads time_coverage_end/_start positionally from this order
    das = client.get("/erddap/griddap/testgrid.das").text
    assert das.index("time_coverage_end") < das.index("time_coverage_start")

    # erddapy and rerddap read the info table by these column names
    info = client.get("/erddap/info/testgrid/index.csv").text
    assert info.splitlines()[0] == "Row Type,Variable Name,Attribute Name,Data Type,Value"

    # rerddap asserts on this exact string, space included (or rather, not)
    info_json = client.get("/erddap/info/testgrid/index.json")
    assert info_json.headers["content-type"] == "application/json;charset=UTF-8"

    # erddapy >=3.2 discovers a griddap dataset from .ncml alone: it derives
    # data variables by subtracting dimension names, and raises if a dimension
    # lacks a space-separated actual_range
    root = ET.fromstring(client.get("/erddap/griddap/testgrid.ncml").text)
    dims = [d.attrib["name"] for d in root.findall(f"{{{NCML_NS}}}dimension")]
    variables = [v.attrib["name"] for v in root.findall(f"{{{NCML_NS}}}variable")]
    assert dims == ["time", "latitude", "longitude"]
    assert set(variables) - set(dims) == {"tos", "sos"}
    for dim in dims:
        el = root.find(
            f'nc:variable[@name="{dim}"]/nc:attribute[@name="actual_range"]',
            namespaces={"nc": NCML_NS},
        )
        assert el is not None, f"{dim} has no actual_range"
        low, high = el.attrib["value"].split()
        assert float(low) <= float(high)

    # xarray opens the .nc as netCDF-3 classic
    resp = client.get("/erddap/griddap/testgrid.nc?tos[0:1:2][0:1:2][0:1:1]")
    assert resp.headers["content-type"] == "application/x-netcdf"
    assert resp.content[:3] == b"CDF", "ERDDAP serves netCDF-3 classic for .nc"
    ds = xr.open_dataset(io.BytesIO(resp.content), engine="scipy")
    assert ds.tos.shape == (3, 3, 2)
    assert ds.time.dtype.kind == "M"

    # erddapy and rerddap read the .json table by these keys
    payload = client.get("/erddap/griddap/testgrid.json?tos[0][0][0]").json()
    assert set(payload["table"]) == {"columnNames", "columnTypes", "columnUnits", "rows"}
    assert payload["table"]["columnNames"] == ["time", "latitude", "longitude", "tos"]


def test_tabledap_index_is_empty_not_404(client):
    """rerddap calls this to classify a datasetID; a 404 breaks info()."""
    resp = client.get("/erddap/tabledap/index.json")
    assert resp.status_code == 200
    assert resp.json()["table"]["rows"] == []


def test_ioos_category_is_filled_in(client):
    body = client.get("/erddap/info/testgrid/index.csv").text
    assert "ioos_category" in body
    assert "Temperature" in body


def test_fully_percent_encoded_csv_request(client):
    """Brackets, colons and commas arrive as %5B %5D %3A %2C and mean the same (#52).

    Code that builds URLs with ``urllib.parse.quote(safe="")`` sends every
    reserved character encoded; nothing else tested decoding.
    """
    plain = (
        "/erddap/griddap/testgrid.csv"
        "?tos[(2020-01-02T00:00:00Z):1:(2020-01-03T00:00:00Z)]"
        "[(42.5):1:(47.5)][(232.0):1:(236.0)],sos[(2020-01-02T00:00:00Z):1:(2020-01-03T00:00:00Z)]"
        "[(42.5):1:(47.5)][(232.0):1:(236.0)]"
    )
    path, query = plain.split("?")
    encoded = path + "?" + quote(query, safe="")
    assert "%5B" in encoded
    assert "%3A" in encoded
    assert "%2C" in encoded
    assert "[" not in encoded

    response = client.get(encoded)
    assert response.status_code == 200
    expected = client.get(plain)
    assert expected.status_code == 200
    assert response.text == expected.text
    df = pd.read_csv(io.StringIO(response.text), skiprows=[1])
    assert len(df) == 2 * 3 * 2
    assert list(df.columns)[-2:] == ["tos", "sos"]


def test_unsupported_filetype_is_400(client):
    resp = client.get("/erddap/griddap/testgrid.mat")
    assert resp.status_code == 400
    assert (
        message(resp) == "Bad Request: Query error: fileType=.mat isn't supported by this dataset."
    )


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
        line.split(",")[2] for line in body.splitlines() if line.startswith("attribute,NC_GLOBAL,")
    ]
    assert names == sorted(names, key=str.lower)
    assert "_xpublish_id" not in names


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
    assert list(ds.latitude.attrs["actual_range"]) == [42.5, 45.0]
    assert "_FillValue" not in ds.latitude.attrs
    assert ds.time.attrs["units"] == "seconds since 1970-01-01T00:00:00Z"
    assert "calendar" not in ds.time.attrs
    assert list(ds.time.attrs["actual_range"]) == [1577923200.0, 1578009600.0]


def test_full_dataset_gets_bounding_box_globals(client):
    """ERDDAP adds *most_* globals even when the source has none."""
    das = client.get("/erddap/griddap/testgrid.das").text
    assert "Float64 Northernmost_Northing 50.0;" in das
    assert "Float64 Easternmost_Easting 240.0;" in das


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
    detail = message(client.get("/erddap/griddap/testgrid"))
    assert "ncml" in detail
    assert "dods" in detail


def test_integer_variable_with_nan_fill_still_serves_metadata():
    """Copilot review: a NaN fill cannot be cast to an integer dtype."""
    ds = xr.Dataset({"n": ("x", np.array([1, 2], dtype="int16"))}, coords={"x": [0, 1]})
    ds.n.encoding.update({"_FillValue": np.nan, "scale_factor": 0.1})
    c = TestClient(xpublish.Rest({"ints": ds}, plugins={"erddap": ErddapPlugin()}).app)
    das = c.get("/erddap/griddap/ints.das")
    assert das.status_code == 200
    assert "_FillValue" not in das.text


def test_router_uses_the_deps_it_is_given(grid_dataset):
    """A caller can hand the router its own Dependencies (xpublish's plugin guide)."""

    deps = Dependencies(
        dataset_ids=lambda: ["custom"],
        datatree=lambda dataset_id: xr.DataTree(grid_dataset),
        cache=lambda: None,
    )
    app = FastAPI()
    app.include_router(ErddapPlugin().app_router(deps))
    client = TestClient(app)

    body = client.get("/erddap/griddap/index.csv").text
    assert "custom" in body
    assert "custom_depth" in body
    assert "testgrid" not in body
    assert client.get("/erddap/griddap/custom.das").status_code == 200


def test_default_deps_resolve_through_overrides(grid_dataset):
    """Default Dependencies() hold placeholders that the app overrides."""

    app = FastAPI()
    app.include_router(ErddapPlugin().app_router(Dependencies()))
    app.dependency_overrides[get_dataset_ids] = lambda: ["overridden"]
    app.dependency_overrides[get_datatree] = lambda dataset_id: xr.DataTree(
        grid_dataset,
    )
    body = TestClient(app).get("/erddap/griddap/index.csv").text
    assert "overridden" in body


@pytest.fixture(scope="module")
def tree_client(grid_dataset):
    """A store whose variables are all in groups, one of them nested."""
    tos = grid_dataset[["tos"]]
    tree = xr.DataTree.from_dict(
        {
            "/": xr.Dataset(attrs={"title": "The whole store"}),
            "/regrid": tos.assign_attrs(title="Regridded"),
            "/native/monthly": tos,
        },
    )
    rest = xpublish.Rest({"store": tree}, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


def test_groups_of_a_datatree_are_datasets(tree_client):
    """Each group with variables is listed; the empty root and parent are not."""
    table = pd.read_csv(io.StringIO(tree_client.get("/erddap/griddap/index.csv").text))
    assert sorted(table["Dataset ID"]) == ["store_native_monthly", "store_regrid"]


def test_group_keeps_its_own_attributes(tree_client):
    body = tree_client.get("/erddap/info/store_regrid/index.csv").text
    assert "Regridded" in body
    assert "The whole store" not in body


def test_group_serves_data(tree_client):
    resp = tree_client.get("/erddap/griddap/store_native_monthly.csv?tos[0][0][0]")
    assert resp.status_code == 200
    assert resp.text.splitlines()[0].startswith("time,")


def test_duplicate_dataset_ids_are_both_refused(grid_dataset, caplog):
    """A store 'a_b' and the group 'b' of a store 'a' would share an id."""
    tos = grid_dataset[["tos"]]
    rest = xpublish.Rest(
        {"a_b": tos, "a": xr.DataTree.from_dict({"/b": tos}), "c": tos},
        plugins={"erddap": ErddapPlugin()},
    )
    with caplog.at_level("ERROR"):
        body = TestClient(rest.app).get("/erddap/griddap/index.csv").text
    table = pd.read_csv(io.StringIO(body))
    assert list(table["Dataset ID"]) == ["c"]
    assert "'a_b'" in caplog.text
    assert "'a/b'" in caplog.text


def test_errors_have_erddaps_body(client):
    """Errors are ERDDAP's plain-text body, which erddapy and rerddap show users (#36)."""
    resp = client.get("/erddap/griddap/nope.csv")
    assert resp.status_code == 404
    assert resp.text == (
        'Error {\n    code=404;\n    message="Not Found: Currently unknown datasetID=nope";\n}\n'
    )
    assert message(client.get("/erddap/info/testgrid/index.foo")) == (
        "Not Found: Unsupported fileType=.foo"
    )
    # quotes are escaped
    assert message(client.get("/erddap/search/index.csv")).startswith(
        'Not Found: A .csv search request must include a query, for example, "?page=1',
    )


def test_unexpected_errors_are_erddap_500s(grid_dataset, monkeypatch):
    """A bug is logged and answered as ERDDAP would, not as a bare traceback."""

    def boom(*args, **kwargs):
        raise RuntimeError("something broke")

    monkeypatch.setattr(plugin_module.formats, "das_response", boom)
    rest = xpublish.Rest({"g": grid_dataset}, plugins={"erddap": ErddapPlugin()})
    resp = TestClient(rest.app, raise_server_exceptions=False).get("/erddap/griddap/g.das")
    assert resp.status_code == 500
    assert message(resp) == "Internal Server Error: RuntimeError: something broke"


@pytest.fixture(scope="module")
def raw_byte_dataset() -> xr.Dataset:
    """An undecoded int8 mask whose _FillValue is in the data (#78).

    The attributes are plain ints, as Zarr's JSON gives them back when a
    store is opened with ``mask_and_scale=False``.
    """
    return xr.Dataset(
        {
            "mask": (
                ("lat", "lon"),
                np.array([[1, 2], [-128, 4]], dtype="int8"),
                {"_FillValue": -128, "flag_masks": [1, 2, 4], "valid_min": 1, "valid_max": 31},
            ),
        },
        coords={"lat": [10.0, 11.0], "lon": [20.0, 21.0]},
    )


@pytest.mark.parametrize("decoded", [True, False], ids=["decoded", "raw"])
def test_masked_integer_is_served_as_its_integer_type(raw_byte_dataset, decoded):
    """An int8 with a _FillValue is a Byte everywhere, as ERDDAP serves it (#78).

    xarray's default decoding (``decode_cf``, as ``open_zarr`` does) turns it
    into float32 with NaN for the fill and the int8 in ``.encoding``; raw,
    the fill is an int attribute. Either way ERDDAP's answer is the same:
    Byte, attributes typed as the variable, and the fill cell missing (NaN
    in csv, null in json, the fill in .nc).
    """
    ds = xr.decode_cf(raw_byte_dataset) if decoded else raw_byte_dataset
    assert (ds.mask.dtype.kind == "f") == decoded
    rest = xpublish.Rest({"m": ds}, plugins={"erddap": ErddapPlugin()})
    client = TestClient(rest.app)
    url = "/erddap/griddap/m"

    assert "Byte mask[latitude = 2][longitude = 2];" in client.get(f"{url}.dds").text
    das = client.get(f"{url}.das").text
    for line in [
        "Byte _FillValue -128;",
        'String _Unsigned "false";',
        "Byte flag_masks 1, 2, 4;",
        "Byte valid_max 31;",
        "Byte valid_min 1;",
    ]:
        assert line in das
    assert (
        '<variable name="mask" shape="latitude longitude" type="byte">'
        in client.get(f"{url}.ncml").text
    )
    assert (
        'variable,mask,,byte,"latitude, longitude"' in client.get("/erddap/info/m/index.csv").text
    )

    rows = client.get(f"{url}.csv0?mask").text.splitlines()
    assert [r.rsplit(",", 1)[1] for r in rows] == ["1", "2", "NaN", "4"]
    table = client.get(f"{url}.json?mask").json()["table"]
    assert table["columnTypes"][-1] == "byte"
    assert [r[-1] for r in table["rows"]] == [1, 2, None, 4]

    body = client.get(f"{url}.nc?mask").content
    with xr.open_dataset(io.BytesIO(body), decode_cf=False) as nc:
        assert nc.mask.dtype == np.int8
        assert nc.mask.attrs["_FillValue"] == -128
        assert nc.mask.values.ravel().tolist() == [1, 2, -128, 4]


#: (dtype, fill, a large value, .dds type, DAS fill text, json type, .nc dtype)
#: as ERDDAP serves them: DAP2 and netCDF-3 have no 64-bit integers or
#: unsigned bytes, and netCDF-3 has no unsigned types at all (#64).
_INTEGER_TYPES = [
    ("int64", -9, 2**40, "Float64", "Float64 _FillValue -9", "long", "float64"),
    ("uint8", 251, 200, "Byte", "Byte _FillValue -5", "ubyte", "int8"),
    ("uint16", 65531, 60000, "UInt16", "UInt16 _FillValue 65531", "ushort", "int16"),
    ("uint32", 2**32 - 5, 4_000_000_000, "UInt32", "UInt32 _FillValue 4294967291", "uint", "int32"),
]


@pytest.mark.parametrize("decoded", [True, False], ids=["decoded", "raw"])
@pytest.mark.parametrize("case", _INTEGER_TYPES, ids=[t[0] for t in _INTEGER_TYPES])
def test_integer_types_are_served_as_erddap_does(case, decoded):
    """No 500s, and the same type in every format, as ERDDAP gives it (#64).

    Mappings from ERDDAP's source (``OpendapHelper.getAtomicType``,
    ``NcHelper.getNc3DataType``/``newAttribute``) and checked on PacIOOS's
    dhw_5km: unsigned data in ``.nc`` is the signed type with
    ``_Unsigned = "true"``, long data is double.
    """
    dtype, fill, big, dds, das, json_type, nc_dtype = case
    raw = xr.Dataset(
        {
            "v": (
                ("lat", "lon"),
                np.array([[1, 2], [fill, big]], dtype=dtype),
                {"_FillValue": np.array(fill, dtype=dtype)[()]},
            ),
        },
        coords={"lat": [10.0, 11.0], "lon": [20.0, 21.0]},
    )
    ds = xr.decode_cf(raw) if decoded else raw
    client = TestClient(xpublish.Rest({"m": ds}, plugins={"erddap": ErddapPlugin()}).app)
    url = "/erddap/griddap/m"

    assert f"{dds} v[latitude = 2][longitude = 2];" in client.get(f"{url}.dds").text
    das_text = client.get(f"{url}.das").text
    assert das in das_text
    assert ('String _Unsigned "true";' in das_text) == (dtype == "uint8")
    assert f'<variable name="v" shape="latitude longitude" type="{json_type}">' in (
        client.get(f"{url}.ncml").text
    )
    rows = client.get(f"{url}.csv0?v").text.splitlines()
    assert [r.rsplit(",", 1)[1] for r in rows] == ["1", "2", "NaN", str(big)]
    table = client.get(f"{url}.json?v").json()["table"]
    assert table["columnTypes"][-1] == json_type
    assert [r[-1] for r in table["rows"]] == [1, 2, None, big]

    resp = client.get(f"{url}.nc?v")
    assert resp.status_code == 200
    with xr.open_dataset(io.BytesIO(resp.content), decode_cf=False) as nc:
        assert nc.v.dtype == np.dtype(nc_dtype)
        assert (nc.v.attrs.get("_Unsigned") == "true") == (dtype[0] == "u")
    with xr.open_dataset(io.BytesIO(resp.content)) as nc:  # what a client reads back
        values = nc.v.values.ravel()
        assert np.isnan(values[2])
        assert values[[0, 1, 3]].tolist() == [1, 2, big]


def test_unsigned_stored_signed_is_unsigned():
    """netCDF-3 stores ubyte as byte with ``_Unsigned = "true"`` (dhw_5km does).

    Opened raw, the attribute is still there and the data signed; ERDDAP
    serves it as ubyte all the same.
    """
    raw = xr.Dataset(
        {
            "v": (
                ("lat", "lon"),
                np.array([[1, -56], [-5, 4]], dtype="int8"),
                {"_FillValue": np.int8(-5), "_Unsigned": "true", "valid_max": np.int8(-6)},
            ),
        },
        coords={"lat": [10.0, 11.0], "lon": [20.0, 21.0]},
    )
    client = TestClient(xpublish.Rest({"m": raw}, plugins={"erddap": ErddapPlugin()}).app)
    info = client.get("/erddap/info/m/index.csv").text
    assert "variable,v,,ubyte," in info
    assert "attribute,v,_FillValue,ubyte,251" in info
    assert "attribute,v,valid_max,ubyte,250" in info
    assert "_Unsigned" not in info
    rows = client.get("/erddap/griddap/m.csv0?v").text.splitlines()
    assert [r.rsplit(",", 1)[1] for r in rows] == ["1", "200", "NaN", "4"]


def test_packed_variable_unpacks_its_fill_and_valid_range():
    """ERDDAP's ``EDV`` unpacks ``_FillValue`` and ``valid_*`` (#64).

    jplMURSST41's analysed_sst, int16 with scale 0.001 and offset 25, has
    ``_FillValue -7.768``, not NaN.
    """
    raw = xr.Dataset(
        {
            "sst": (
                ("lat", "lon"),
                np.array([[0, 1000], [-32768, 2000]], dtype="int16"),
                {
                    "_FillValue": np.int16(-32768),
                    "scale_factor": 0.001,
                    "add_offset": 25.0,
                    "valid_min": np.int16(-32767),
                    "valid_max": np.int16(32767),
                },
            ),
        },
        coords={"lat": [10.0, 11.0], "lon": [20.0, 21.0]},
    )
    client = TestClient(
        xpublish.Rest({"m": xr.decode_cf(raw)}, plugins={"erddap": ErddapPlugin()}).app,
    )
    das = client.get("/erddap/griddap/m.das").text
    assert "Float64 _FillValue -7.768000000000001;" in das
    assert "Float64 valid_min -7.767000000000003;" in das  # as coastwatch writes it
    assert "Float64 valid_max 57.767;" in das
    rows = client.get("/erddap/griddap/m.csv0?sst").text.splitlines()
    assert [r.rsplit(",", 1)[1] for r in rows] == ["25.0", "26.0", "NaN", "27.0"]
    with xr.open_dataset(io.BytesIO(client.get("/erddap/griddap/m.nc?sst").content)) as nc:
        assert np.isnan(nc.sst.values[1, 0])
