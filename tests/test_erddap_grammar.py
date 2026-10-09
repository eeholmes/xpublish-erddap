"""Small differences from ERDDAP's output and grammar (#71).

Each test names the ERDDAP class and method it follows. Data is built in
memory (``xr.decode_cf`` gives what a default open gives), because CI has no
zarr.
"""

import io

import numpy as np
import pytest
import xarray as xr
import xpublish
from error_body import message
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin


def gridded(n_time: int = 3, n_lat: int = 4, n_lon: int = 5) -> xr.Dataset:
    """A time/lat/lon store whose time says ``calendar`` and whose data says ``coordinates``."""
    raw = xr.Dataset(
        {
            "sst": (
                ("time", "latitude", "longitude"),
                np.arange(n_time * n_lat * n_lon, dtype="float32").reshape(n_time, n_lat, n_lon),
                {"units": "degree_C", "coordinates": "time latitude longitude"},
            ),
        },
        coords={
            "time": (
                "time",
                np.arange(n_time, dtype="float64"),
                {"units": "days since 2020-01-01", "calendar": "gregorian"},
            ),
            "latitude": ("latitude", np.linspace(10.0, 40.0, n_lat), {"units": "degrees_north"}),
            "longitude": ("longitude", np.linspace(100.0, 140.0, n_lon), {"units": "degrees_east"}),
        },
    )
    return xr.decode_cf(raw)


@pytest.fixture(scope="module")
def client():
    rest = xpublish.Rest({"g": gridded()}, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


# -- calendar and coordinates (EDV passes source attributes through) -----------
def test_calendar_and_coordinates_are_served(client):
    das = client.get("/erddap/griddap/g.das").text
    time_block = das.split("time {")[1].split("}")[0]
    assert 'String calendar "gregorian";' in time_block
    assert 'units "seconds since 1970-01-01T00:00:00Z"' in time_block
    assert 'String coordinates "time latitude longitude";' in das.split("sst {")[1].split("}")[0]


def test_calendar_and_coordinates_are_in_ncml_info_and_nc(client):
    ncml = client.get("/erddap/griddap/g.ncml").text
    assert '<attribute name="calendar" value="gregorian" />' in ncml
    assert '<attribute name="coordinates" value="time latitude longitude" />' in ncml
    info = client.get("/erddap/info/g/index.csv").text
    assert "attribute,time,calendar,String,gregorian" in info
    assert "attribute,sst,coordinates,String,time latitude longitude" in info
    nc = xr.open_dataset(io.BytesIO(client.get("/erddap/griddap/g.nc?sst[0][0][0]").content))
    assert nc.time.attrs.get("calendar", nc.time.encoding.get("calendar")) == "gregorian"
    assert nc.sst.attrs.get("coordinates", nc.sst.encoding.get("coordinates"))


# -- a one-value axis (Erddap.doInfo, EDVGridAxis.destinationToString) ---------
def one_value_axes() -> xr.Dataset:
    return xr.Dataset(
        {"v": (("time", "altitude", "latitude", "level", "longitude"), np.ones((1, 1, 1, 1, 3)))},
        coords={
            "time": ("time", np.array(["2020-02-03T04:05:06"], dtype="datetime64[ns]")),
            "altitude": ("altitude", np.array([0.0]), {"units": "m"}),
            "latitude": ("latitude", np.array([34.5], dtype="float32"), {"units": "degrees_north"}),
            "level": ("level", np.array([5], dtype="int32"), {"units": "1"}),
            "longitude": ("longitude", [10.0, 11.0, 12.0], {"units": "degrees_east"}),
        },
    )


def with_altitude() -> xr.Dataset:
    return xr.Dataset(
        {"v": (("time", "altitude", "latitude"), np.ones((3, 3, 4), dtype="float32"))},
        coords={
            "time": ("time", np.array(["2020-01-01", "2020-01-02", "2020-01-03"], "M8[ns]")),
            "altitude": ("altitude", np.array([0.0, 10.0, 20.0]), {"units": "m"}),
            "latitude": ("latitude", np.linspace(10.0, 40.0, 4), {"units": "degrees_north"}),
        },
        attrs={
            "geospatial_vertical_min": 0.0,
            "geospatial_vertical_max": 20.0,
            "geospatial_vertical_units": "m",
            "geospatial_vertical_positive": "up",
            "geospatial_vertical_resolution": 10.0,
        },
    )


def globals_of_nc(client, query: str) -> dict:
    r = client.get(f"/erddap/griddap/alt.nc?{query}")
    assert r.status_code == 200, r.text
    return xr.open_dataset(io.BytesIO(r.content), decode_times=False).attrs


def test_axis_only_nc_drops_coverage_of_axes_not_asked_for():
    """``AxisDataAccessor`` removes vertical and time coverage, then sets the axes asked for."""
    rest = xpublish.Rest({"alt": with_altitude()}, plugins={"erddap": ErddapPlugin()})
    client = TestClient(rest.app)
    lat = globals_of_nc(client, "latitude[0:1:1]")
    assert "geospatial_lat_min" in lat
    for key in (
        "geospatial_vertical_min",
        "geospatial_vertical_max",
        "geospatial_vertical_units",
        "geospatial_vertical_positive",
        "time_coverage_start",
        "time_coverage_end",
    ):
        assert key not in lat, key
    assert lat["geospatial_vertical_resolution"] == 10.0  # ERDDAP leaves it
    alt = globals_of_nc(client, "altitude[1:1:2]")
    assert (alt["geospatial_vertical_min"], alt["geospatial_vertical_max"]) == (10.0, 20.0)
    assert alt["geospatial_vertical_positive"] == "up"
    assert alt["geospatial_vertical_units"] == "m"
    assert "geospatial_lat_min" not in alt
    assert "time_coverage_start" not in alt
    time = globals_of_nc(client, "time[1:1:2]")
    assert time["time_coverage_start"] == "2020-01-02T00:00:00Z"
    assert "geospatial_vertical_min" not in time


def test_data_nc_vertical_coverage_describes_the_subset():
    rest = xpublish.Rest({"alt": with_altitude()}, plugins={"erddap": ErddapPlugin()})
    attrs = globals_of_nc(TestClient(rest.app), "v[0:1:2][0:1:1][0:1:3]")
    assert (attrs["geospatial_vertical_min"], attrs["geospatial_vertical_max"]) == (0.0, 10.0)


# -- axis-only tables of unequal lengths (Table.makeColumnsSameSize) ------------
def test_axis_only_csv_pads_numbers_with_nan_and_time_with_blank(client):
    r = client.get("/erddap/griddap/g.csv?time[0:1:2],longitude[0:1:4],latitude[0:1:3]")
    assert r.text.splitlines()[2:] == [
        "2020-01-01T00:00:00Z,100.0,10.0",
        "2020-01-02T00:00:00Z,110.0,20.0",
        "2020-01-03T00:00:00Z,120.0,30.0",
        ",130.0,40.0",
        ",140.0,NaN",
    ]


def test_axis_only_json_pads_with_null(client):
    r = client.get("/erddap/griddap/g.json?time[0:1:2],longitude[0:1:4]")
    assert r.json()["table"]["rows"][-2:] == [[None, 130.0], [None, 140.0]]
    r = client.get("/erddap/griddap/g.json?latitude[0:1:3],longitude[0:1:4]")
    assert r.json()["table"]["rows"][-1] == [None, 140.0]


# -- NcML entities (XML.encodeAsXML, already in place since #64) ---------------------
def test_ncml_escapes_percent_as_a_numeric_entity():
    ds = gridded(2, 2, 2)
    ds.attrs["comment"] = '100% <ice> & "snow"'
    ds["sst"].attrs["long_name"] = "0 is 0% ice"
    rest = xpublish.Rest({"pct": ds}, plugins={"erddap": ErddapPlugin()})
    ncml = TestClient(rest.app).get("/erddap/griddap/pct.ncml").text
    assert 'name="comment" value="100&#37; &lt;ice&gt; &amp; &quot;snow&quot;"' in ncml
    assert 'name="long_name" value="0 is 0&#37; ice"' in ncml
    assert "%" not in ncml.replace("&#37;", "")


# -- .json: infinite numbers (String2.toJson(double)) -------------------------------
def test_json_writes_null_for_infinite_numbers():
    ds = gridded(1, 2, 2)
    ds["sst"].values[0, 0, :] = [np.inf, -np.inf]
    rest = xpublish.Rest({"inf": ds}, plugins={"erddap": ErddapPlugin()})
    r = TestClient(rest.app).get("/erddap/griddap/inf.json?sst[0][0:1][0:1]")
    assert "Infinity" not in r.text
    rows = r.json()["table"]["rows"]  # valid JSON: json.loads would also take Infinity
    assert [row[-1] for row in rows] == [None, None, 2.0, 3.0]


def test_one_value_axis_info_says_only_value():
    rest = xpublish.Rest({"one": one_value_axes()}, plugins={"erddap": ErddapPlugin()})
    text = TestClient(rest.app).get("/erddap/info/one/index.csv").text
    rows = {r.split(",", 2)[1]: r for r in text.splitlines() if r.startswith("dimension,")}
    assert rows["time"].endswith('"nValues=1, onlyValue=2020-02-03T04:05:06Z"')
    assert rows["altitude"].endswith('"nValues=1, onlyValue=0.0"')
    assert rows["latitude"].endswith('"nValues=1, onlyValue=34.5"')
    assert rows["level"].endswith('"nValues=1, onlyValue=5.0"')
    assert rows["longitude"].endswith('"nValues=3, evenlySpaced=true, averageSpacing=1.0"')


# -- the grammar: what ERDDAP refuses and accepts -----------------------------------
# Messages and positions are as erddap.ioos.us (ERDDAP 2.31) answers the same
# shapes on etopo5_EDDGridCopy (ROSE[latitude][longitude]); the positions here
# are those of this dataset's longer queries.
FULL = "sst[0:1:1][0:1:1][0:1:1]"  # 24 characters


def query_message(response) -> str:
    return message(response).removeprefix("Bad Request: ")


def query_error(client, query: str, ext: str = "csv") -> str:
    r = client.get(f"/erddap/griddap/g.{ext}?{query}")
    assert r.status_code == 400, (query, r.status_code, r.text[:200])
    return query_message(r)


# an empty start or stop, and a stride that is not an integer
# (EDDGrid.parseAxisBrackets, String2.parseInt)
@pytest.mark.parametrize(
    ("selector", "text"),
    [
        ("[:1:2]", 'Start="" is invalid.  It must be an integer between 0 and 2.'),
        ("[:2]", 'Start="" is invalid.  It must be an integer between 0 and 2.'),
        ("[:]", 'Start="" is invalid.  It must be an integer between 0 and 2.'),
        ("[0:]", 'Stop="" is invalid.  It must be an integer between 0 and 2.'),
        ("[0:1:]", 'Stop="" is invalid.  It must be an integer between 0 and 2.'),
        ("[0::2]", "Stride= is invalid."),
        ("[0:0:2]", "Stride=0 is invalid."),
        ("[0:-1:2]", "Stride=-1 is invalid."),
        ("[0:abc:2]", "Stride=abc is invalid."),
        ("[()]", "The Start value inside () is missing."),
        ("[0:1:()]", "The Stop value inside () is missing."),
    ],
)
def test_empty_and_bad_parts_of_a_range_are_refused(client, selector, text):
    got = query_error(client, f"sst{selector}[0][0]")
    assert got == (f'Query error: For variable=sst axis#0=time Constraint="{selector}": {text}')


def test_an_empty_bracket_is_the_whole_axis(client):
    r = client.get("/erddap/griddap/g.csv?sst[][][]")
    assert r.status_code == 200
    assert r.text == client.get("/erddap/griddap/g.csv?sst").text


@pytest.mark.parametrize(("stride", "rows"), [("1.4", 3), ("1.5", 2), ("2.5", 1), ("0x2", 2)])
def test_a_stride_is_rounded_as_string2_parseint_does(client, stride, rows):
    """erddap.ioos.us: ``[0:1.5:2]`` serves indices 0 and 2, as stride 2 does."""
    r = client.get(f"/erddap/griddap/g.csv?time[0:{stride}:2]")
    assert r.status_code == 200
    assert len(r.text.splitlines()) == 2 + rows


# &.jsonp= (Erddap.doGet, TableWriterJson, String2.isJsonpNameSafe)
def test_jsonp_wraps_a_json_response(client):
    plain = client.get("/erddap/griddap/g.json?time[0:1:1]")
    r = client.get("/erddap/griddap/g.json?time[0:1:1]&.jsonp=handle.it")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/javascript;charset=UTF-8"
    assert r.text == f"handle.it({plain.text}\n)"
    assert plain.headers["content-type"] == "application/json;charset=UTF-8"


def test_jsonp_on_a_data_request(client):
    r = client.get(f"/erddap/griddap/g.json?{FULL}&.jsonp=cb")
    assert r.status_code == 200
    assert r.text.startswith('cb({\n  "table"')
    assert r.text.endswith("}\n)")


def test_jsonp_wraps_the_info_table(client):
    r = client.get("/erddap/info/g/index.json?&.jsonp=cb")
    assert r.headers["content-type"] == "application/javascript;charset=UTF-8"
    assert r.text.startswith('cb({\n  "table"')
    assert r.text.endswith("}\n)")
    assert client.get("/erddap/info/g/index.csv?&.jsonp=cb").text.startswith("Row Type,")


def test_jsonp_is_for_json_only(client):
    for ext in ("csv", "csvp", "nc"):
        r = client.get(f"/erddap/griddap/g.{ext}?time[0:1:1]&.jsonp=cb")
        assert r.status_code == 200
        assert not r.content.startswith(b"cb(")


@pytest.mark.parametrize("name", ["1abc", "bad-name", "a.", ".a", "a..b", "a b", "x" * 256])
def test_a_bad_jsonp_name_is_refused(client, name):
    for url in (
        f"/erddap/griddap/g.json?time[0:1:1]&.jsonp={name}",
        f"/erddap/info/g/index.json?&.jsonp={name}",
    ):
        r = client.get(url)
        assert r.status_code == 400, url
        assert query_message(r).startswith("Query error: That jsonp functionName isn't allowed.")
        assert name not in query_message(r)  # ERDDAP does not echo a possibly malicious name


def test_jsonp_head_says_javascript(client):
    r = client.head("/erddap/griddap/g.json?time[0:1:1]&.jsonp=cb")
    assert r.headers["content-type"] == "application/javascript;charset=UTF-8"


# &-clauses (EDDGrid.parseDataDapQuery / parseAxisDapQuery, Table.getDapQueryParts)
def test_and_clauses_that_start_with_a_dot_are_ignored(client):
    plain = client.get(f"/erddap/griddap/g.csv?{FULL}")
    assert client.get(f"/erddap/griddap/g.csv?{FULL}&.draw=surface").text == plain.text
    assert client.get(f"/erddap/griddap/g.csv?{FULL}&.draw=surface&.vars=a|b").text == plain.text
    axis = client.get("/erddap/griddap/g.csv?time[0:1:1]")
    assert client.get("/erddap/griddap/g.csv?time[0:1:1]&.draw=lines").text == axis.text


def test_an_and_clause_alone_asks_for_the_whole_dataset(client):
    whole = client.get("/erddap/griddap/g.csv")
    r = client.get("/erddap/griddap/g.csv?&.draw=surface")
    assert r.status_code == 200
    assert r.text == whole.text
    assert (
        client.get("/erddap/griddap/g.dds?&.draw=surface").text
        == client.get(
            "/erddap/griddap/g.dds",
        ).text
    )


def test_jsonp_on_a_whole_dataset_request(client):
    r = client.get("/erddap/griddap/g.json?&.jsonp=cb")
    assert r.status_code == 200
    assert r.text.startswith('cb({\n  "table"')


def test_a_comma_in_an_and_clause_is_not_a_variable(client):
    r = client.get(f"/erddap/griddap/g.csv?{FULL}&.vars=longitude|latitude|sst,nosuchvariable")
    assert r.status_code == 200
    assert r.text == client.get(f"/erddap/griddap/g.csv?{FULL}").text


@pytest.mark.parametrize("query", [f"{FULL}&foo", f"{FULL}&", f"{FULL}&&.draw=surface", "&", "&x"])
def test_an_and_clause_must_start_with_a_dot(client, query):
    assert query_error(client, query) == (
        "Query error: In a griddap query, '&' must be followed by a .graphicsCommand."
    )


def test_an_unclosed_quote_is_refused(client):
    assert query_error(client, f'{FULL}&.title="x') == (
        "Query error: A closing doublequote is missing."
    )


# text outside the brackets (EDDGrid.parseDataDapQuery, parseAxisDapQuery)
def test_without_the_ampersand_a_graphics_command_is_a_variable(client):
    assert query_error(client, ".draw=surface") == "unknown variable '.draw=surface'"


def test_text_after_an_axis_request_is_refused(client):
    assert query_error(client, "time[(last)]garbage") == (
        'Query error: "g" was not expected at position=13.'
    )
    assert (
        query_error(client, "time[0:1:1]]") == 'Query error: "]" was not expected at position=12.'
    )
    assert query_error(client, "time[0][1]") == 'Query error: "[" was not expected at position=8.'


@pytest.mark.parametrize(
    ("query", "text"),
    [
        (
            f"{FULL}x[0][0]",
            '"," or "[end of query]" was expected at or after position=24, not "x".',
        ),
        (
            f"{FULL}garbage",
            '"," or "[end of query]" was expected at or after position=24, not "g".',
        ),
        (f"{FULL},sst", '"[" was expected at or after position=25, not [end of query].'),
        (
            "sst[0:1:1][0:1:1]",
            'For variable=sst axis#2=longitude: "[" was expected at or after position=17, '
            "not [end of query].",
        ),
        (
            "sst[0:1:1][0:1:1]x[0]",
            'For variable=sst axis#2=longitude: "[" was expected at or after position=17, not "x".',
        ),
        (
            "sst[0:1:1[0:1:1][0]",
            'For variable=sst axis#0=time Constraint="[0:1:1[0:1:1]": '
            'Stop="1[0:1:1" is invalid.  It must be an integer between 0 and 2.',
        ),
        (
            "sst[0:1:1",
            'For variable=sst axis#0=time: "]" was not found after position=3.',
        ),
    ],
)
def test_text_after_a_data_request_is_refused(client, query, text):
    assert query_error(client, query).removeprefix("Query error: ") == text


# duplicate variables and axis + data (EDDGrid.parseDataDapQuery, parseAxisDapQuery)
@pytest.mark.parametrize(
    ("query", "text"),
    [
        ("time,time", "Variable name=time occurs twice."),
        ("time[0:1:1],latitude,time", "Variable name=time occurs twice."),
        (f"{FULL},{FULL}", "Variable name=sst occurs twice."),
        ("sst,sst", "Variable name='sst' occurs twice."),
        (
            f"time[0:1:1],{FULL}",
            "A griddap axis variable query can't include a data variable (sst).",
        ),
        ("time,sst", "A griddap axis variable query can't include a data variable (sst)."),
        ("sst,time", "A griddap data variable query can't include an axis variable (time)."),
        (
            f"{FULL},time[0:1:1]",
            "A griddap data variable query can't include an axis variable (time).",
        ),
    ],
)
def test_duplicate_and_mixed_variables_are_refused(client, query, text):
    assert query_error(client, query) == f"Query error: {text}"


def test_two_variables_with_one_subset_are_still_served():
    ds = gridded(2, 2, 2)
    ds["sst2"] = ds["sst"] * 2
    rest = xpublish.Rest({"two": ds}, plugins={"erddap": ErddapPlugin()})
    r = TestClient(rest.app).get(
        "/erddap/griddap/two.csv?sst[0:1:1][0][0:1:1],sst2[0:1:1][0][0:1:1]",
    )
    assert r.status_code == 200
    assert r.text.splitlines()[0] == "time,latitude,longitude,sst,sst2"
