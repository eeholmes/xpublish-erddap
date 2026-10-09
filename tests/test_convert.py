"""``/erddap/convert/*``: refused as on an ERDDAP with its converters off (#70).

Interpolate is a future extension (#98). Until then every converter answers
at once with ``Erddap.doConvert``'s "disabled" 404, in ERDDAP's error form,
instead of FastAPI's JSON 404.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin

DISABLED = (
    "Error {\n"
    "    code=404;\n"
    '    message="Not Found: The \\"convert\\" system has been disabled on this ERDDAP.";\n'
    "}\n"
)

#: rerddapXtracto's ``erddap_interp`` request, and rerddap's converters.
PATHS = [
    "convert/interpolate.csv?TimeLatLonTable=time,latitude,longitude%0A"
    "2020-01-01T00:00:00Z,1,2%0A&requestCSV=sst/sst/Bilinear/4",
    "convert/time.txt?n=0&units=seconds%20since%201970-01-01",
    "convert/units.txt?UDUNITS=degree_C",
    "convert/keywords.txt?standardName=sea_surface_temperature",
    "convert/index.html",
    "convert/nope",
]


@pytest.fixture(scope="module")
def client():
    ds = xr.Dataset(
        {"sst": (("lat", "lon"), np.zeros((2, 3)))},
        coords={"lat": [1.0, 2.0], "lon": [1.0, 2.0, 3.0]},
    )
    rest = xpublish.Rest({"sst": ds}, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


@pytest.mark.parametrize("path", PATHS)
def test_every_converter_is_refused_as_disabled(client, path):
    resp = client.get(f"/erddap/{path}")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == DISABLED


def test_and_on_a_per_dataset_root(client):
    """One path is enough: the per-dataset root reaches the same one-line route."""
    resp = client.get(f"/datasets/sst/erddap/{PATHS[0]}")
    assert resp.status_code == 404
    assert resp.text == DISABLED


def test_head_is_refused_the_same_way(client):
    assert client.head("/erddap/convert/interpolate.csv").status_code == 404
