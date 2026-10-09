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
