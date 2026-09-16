"""xpublish-erddap served below a per-store path, as Flux would serve it.

The test server mounts a CEFI-like store at ``STORE_PREFIX``, so its ERDDAP
root is ``.../regrid/main/erddap``, beside the store's ``.../opendap``. Users
point their ERDDAP code at that root; every URL we hand back must keep the
prefix, or a client following it lands on the wrong server path.
"""

import sys

import httpx
import numpy as np
import pandas as pd
import pytest
from tutorial_data import STORE_PREFIX, tos

erddapy = pytest.importorskip("erddapy")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Live server tests are unreliable on Windows Github Actions workers",
)

#: The catalog's naming rule applied to the store's id
#: "cefi-nep-hindcast-daily/regrid"; the 4-D variables split out.
SURFACE = "cefi_nep_hindcast_daily_regrid"
DEPTH = "cefi_nep_hindcast_daily_regrid_z_l"


@pytest.fixture
def store_root(xpublish_server):
    """The store's ERDDAP root URL."""
    return xpublish_server.replace("/erddap", f"{STORE_PREFIX}/erddap")


def test_catalog_urls_keep_the_store_prefix(store_root):
    """Links in the catalog and search results point back into the store."""
    for path in ("info/index.csv", "search/index.csv?searchFor=cefi"):
        table = httpx.get(f"{store_root}/{path}", timeout=30).text
        assert f"{store_root}/griddap/{SURFACE}" in table
        assert f"{store_root}/info/{DEPTH}/index.json" in table
    for link in (
        f"{store_root}/griddap/{SURFACE}.das",
        f"{store_root}/info/{DEPTH}/index.csv",
    ):
        assert httpx.get(link, timeout=30).status_code == 200


def test_ncml_location_is_the_store_url(store_root):
    ncml = httpx.get(f"{store_root}/griddap/{SURFACE}.ncml", timeout=30).text
    assert f'location="{store_root}/griddap/{SURFACE}"' in ncml


def test_erddapy_works_against_the_store(store_root):
    """Plain erddapy code, with only the server URL changed."""
    e = erddapy.ERDDAP(server=store_root, protocol="griddap", response="nc")
    e.dataset_id = SURFACE
    e.griddap_initialize()
    assert e.variables == ["tos"]
    e.constraints.update(
        {
            "time>=": "2020-01-02T00:00:00Z",
            "time<=": "2020-01-04T00:00:00Z",
            "lat>=": 22.0,
            "lat<=": 23.0,
            "lon>=": 231.0,
            "lon<=": 232.0,
        },
    )
    ds = e.to_xarray()
    assert ds.tos.shape == (3, 3, 3)
    times = pd.to_datetime(ds.time.values).values
    expected = tos(
        times[:, None, None],
        ds.lat.values[None, :, None],
        ds.lon.values[None, None, :],
    )
    np.testing.assert_allclose(ds.tos.values, expected)


def test_erddapy_finds_the_split_dataset(store_root):
    """The store's 4-D variables are a second datasetID under the same root."""
    e = erddapy.ERDDAP(server=store_root, protocol="griddap", response="csvp")
    e.dataset_id = DEPTH
    e.griddap_initialize()
    assert e.variables == ["thetao"]
    assert e.dim_names == ["time", "z_l", "lat", "lon"]
    e.constraints.update({"lat>=": 25.0, "lat<=": 25.0, "lon>=": 235.0, "lon<=": 235.0})
    df = e.to_pandas()
    assert list(df["z_l (meter)"]) == [2.5, 10.0, 50.0]
