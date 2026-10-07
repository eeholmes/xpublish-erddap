"""Response-size limits: refuse too-large requests before reading any data.

Real ERDDAP refuses a ``.nc`` response over 2 GB with a 413 (captured from
coastwatch.pfeg.noaa.gov on 2026-10-05)::

    Payload Too Large: Your query produced too much data.  Try to request
    less data. [memory]  126293 MB is more than the .nc 2 GB limit.

It streams csv and json without a limit. We build every response in memory,
so ``max_response_mb`` lets a server cap all of them.

This is not a parity case: ``tests/parity/capture.py`` snapshots every data
block a request reads, which for a too-large request is the whole variable.
The parity tests also compare only the status of error responses, never the
body, so the wording is checked here against the capture above.
"""

import numpy as np
import pytest
import xarray as xr
import xpublish
from error_body import message
from fastapi.testclient import TestClient
from tutorial_data import _lazy

from xpublish_erddap import ErddapPlugin

#: 1000 x 1000 x 1000 float32: 3815 MB, so over the .nc 2 GB limit.
N = 1000
#: One time step of the grid: 1000 x 1000 float32 = 3.8 MB.
ONE_STEP = "v[0][0:1:999][0:1:999]"


def unreadable(*_):
    """Formula for a grid that must never be read."""
    msg = "data was read for a request that should have been refused"
    raise AssertionError(msg)


def readable(t, y, x):
    return (t + y + x).astype("float32")


def grid(formula) -> xr.Dataset:
    axis = np.arange(N, dtype="float64")
    return xr.Dataset(
        {
            "v": _lazy(
                ("time", "lat", "lon"),
                [axis, axis, axis],
                "float32",
                formula,
                {},
            ),
        },
        coords={"time": axis, "lat": axis, "lon": axis},
        attrs={"title": "limits", "summary": "s", "institution": "i"},
    )


def client(formula=unreadable, **options) -> TestClient:
    rest = xpublish.Rest(
        {"g": grid(formula)},
        plugins={"erddap": ErddapPlugin(strict_axes=False, **options)},
    )
    return TestClient(rest.app, raise_server_exceptions=False)


def detail(response) -> str:
    return message(response)


@pytest.mark.parametrize("ext", ["nc", "csv", "csvp", "csv0", "json"])
def test_configured_limit_refuses_every_data_format(ext):
    r = client(max_response_mb=1).get(f"/erddap/griddap/g.{ext}?{ONE_STEP}")
    assert r.status_code == 413
    assert detail(r) == (
        "Payload Too Large: Your query produced too much data.  "
        "Try to request less data. [memory]  4 MB is more than "
        "this server's 1 MB limit."
    )


def test_under_the_limit_is_served():
    r = client(readable, max_response_mb=5).get(f"/erddap/griddap/g.nc?{ONE_STEP}")
    assert r.status_code == 200


def test_whole_variable_nc_hits_erddaps_2gb_limit_without_a_configured_one():
    r = client().get("/erddap/griddap/g.nc?v")
    assert r.status_code == 413
    assert detail(r).endswith("3815 MB is more than the .nc 2 GB limit.")


def test_the_smaller_limit_is_reported():
    r = client(max_response_mb=100).get("/erddap/griddap/g.nc?v")
    assert detail(r).endswith("this server's 100 MB limit.")


def test_metadata_requests_are_not_limited():
    c = client(max_response_mb=1)
    for path in ("g.das", "g.dds?v", "g.ncml"):
        assert c.get(f"/erddap/griddap/{path}").status_code == 200, path


def test_axis_only_request_counts_only_the_axis():
    r = client(max_response_mb=1).get("/erddap/griddap/g.csv?time")
    assert r.status_code == 200


def test_strides_shrink_the_estimate():
    r = client(readable, max_response_mb=1).get(
        "/erddap/griddap/g.csv?v[0][0:4:999][0:4:999]",
    )
    assert r.status_code == 200
