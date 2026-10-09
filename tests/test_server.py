"""Test real ERDDAP clients against the Xpublish ERDDAP plugin.

These run against a live server over a socket, because the whole point of the
package is that unmodified `erddapy` (and `rerddap`) code works. The
`TestClient` suite in `test_api.py` cannot catch problems that only appear with
a real HTTP client -- content-type handling and percent-encoding among them.
"""

import sys

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from tutorial_data import sst

erddapy = pytest.importorskip("erddapy")
search_servers = pytest.importorskip("erddapy.multiple_server_search").search_servers

# The live-server tests bind a socket and read netCDF from memory; both are
# flaky on the Windows runners. xpublish-opendap skips its live tests there
# for the same reason.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Live server tests are unreliable on Windows Github Actions workers",
)


@pytest.fixture
def erddap(xpublish_server):
    """An erddapy client pointed at the test server."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap", response="nc")
    e.dataset_id = "air"
    return e


def test_griddap_initialize(erddap):
    """erddapy discovers dimensions and variables from the DDS and csvp."""
    assert erddap.dim_names == ["time", "latitude", "longitude"]
    assert erddap.variables == ["air"]
    for dim in ("time", "latitude", "longitude"):
        assert f"{dim}>=" in erddap.constraints
        assert f"{dim}_step" in erddap.constraints


def test_to_xarray_with_coordinate_constraints(erddap, dataset):
    """A coordinate-value subset round-trips into an xarray Dataset."""
    erddap.constraints.update(
        {
            "time>=": "2013-01-05T00:00:00Z",
            "time<=": "2013-01-08T00:00:00Z",
            "latitude>=": 40.0,
            "latitude<=": 50.0,
            "longitude>=": 240.0,
            "longitude<=": 250.0,
        },
    )
    ds = erddap.to_xarray()

    assert set(ds.sizes) == {"time", "latitude", "longitude"}
    assert ds.time.size == 13
    assert ds.latitude.max() <= 50.0
    assert ds.latitude.min() >= 40.0

    # ERDDAP's stop value is the nearest matching step, so the window ends at
    # 2013-01-08T00:00Z -- not at the end of that day, as a pandas slice would.
    expected = dataset.sel(
        time=slice("2013-01-05T00:00", "2013-01-08T00:00"),
        lat=slice(50.0, 40.0),
        lon=slice(240.0, 250.0),
    )
    np.testing.assert_allclose(
        ds.air.values,
        expected.air.values,
        rtol=1e-5,
    )


def test_to_pandas_csv(erddap):
    """The csv response parses into a long-form DataFrame."""
    erddap.response = "csv"
    erddap.constraints.update(
        {"latitude>=": 45.0, "latitude<=": 47.5, "longitude>=": 240.0, "longitude<=": 242.5},
    )
    df = erddap.to_pandas()

    assert list(df.columns) == [
        "time (UTC)",
        "latitude (degrees_north)",
        "longitude (degrees_east)",
        "air (degK)",
    ]
    assert len(df) > 0


def test_griddap_initialize_on_the_split_dataset(xpublish_server):
    """The extra hypercube is usable, not just listed."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap", response="nc")
    e.dataset_id = "mixed_level"
    # expand_dims puts the new dimension first, and the catalog preserves
    # the source's dimension order
    assert e.dim_names == ["level", "time", "latitude", "longitude"]
    assert e.variables == ["air_levels"]


@pytest.mark.parametrize("search_for", ["all", None])
def test_erddapy_search_lists_every_dataset(xpublish_server, search_for):
    """erddapy's search for "all", or with no words, lists the whole catalog (#19)."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap")
    every = set(pd.read_csv(f"{xpublish_server}/griddap/index.csv")["Dataset ID"])
    found = pd.read_csv(e.get_search_url(search_for=search_for, response="csv"))
    assert set(found["Dataset ID"]) == every


def test_erddapy_get_var_by_attr(xpublish_server):
    """get_var_by_attr reads attributes from the info csv (axis and standard_name)."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap")
    dataset_id = "CRW_sst_v1_0_monthly"
    assert e.get_var_by_attr(dataset_id, axis="X") == ["longitude"]
    assert e.get_var_by_attr(dataset_id, axis="Y") == ["latitude"]
    assert e.get_var_by_attr(dataset_id, standard_name="sea_surface_temperature") == [
        "analysed_sst",
    ]
    # the erddapy docs' callable form: every axis variable
    axes = e.get_var_by_attr(dataset_id, axis=lambda v: v in ["X", "Y", "Z", "T"])
    assert sorted(axes) == ["latitude", "longitude", "time"]


def _small_crw(xpublish_server):
    """An erddapy client for a small box of the CRW stand-in."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap", response="nc")
    e.dataset_id = "CRW_sst_v1_0_monthly"
    e.griddap_initialize()
    e.constraints.update(
        {
            "time>=": "2018-01-01T12:00:00Z",
            "time<=": "2018-03-01T12:00:00Z",
            "latitude>=": 17.0,
            "latitude<=": 18.0,
            "longitude>=": 195.0,
            "longitude<=": 196.0,
        },
    )
    return e


def test_erddapy_download_file(xpublish_server, tmp_path, monkeypatch):
    """download_file("nc") saves the griddap .nc response to the working directory."""
    monkeypatch.chdir(tmp_path)
    path = _small_crw(xpublish_server).download_file("nc")
    assert path.suffix == ".nc"
    with xr.open_dataset(tmp_path / path) as ds:
        assert ds.analysed_sst.shape == (3, 21, 21)
        expected = sst(
            ds.time.values[:, None, None],
            ds.latitude.values[None, :, None],
            ds.longitude.values[None, None, :],
        )
        np.testing.assert_allclose(ds.analysed_sst.values, expected)


@pytest.mark.skipif(
    "erddapy" not in xr.backends.list_engines(),
    reason="erddapy's xarray backend does not load with the lowest-version xarray "
    "(it imports T_PathFileOrDataStore, which that xarray lacks): an erddapy/xarray "
    "mismatch, not ours. The min-deps job is the only one that skips this.",
)
def test_xarray_engine_erddapy(xpublish_server):
    """xr.open_dataset(url, engine="erddapy") opens a griddap .nc URL."""
    e = _small_crw(xpublish_server)
    ds = xr.open_dataset(e.get_download_url(response="nc"), engine="erddapy")
    assert ds.analysed_sst.shape == (3, 21, 21)
    assert ds.analysed_sst.attrs["units"] == "degree_C"


def test_erddapy_search_servers(xpublish_server):
    """search_servers over a server list of one (ours), so nothing leaves the machine."""
    # erddapy's own server list ends every URL with a slash and builds
    # "{server}search/index.csv" from it
    server = f"{xpublish_server}/"
    found = search_servers("CRW_sst", servers_list=[server], protocol="griddap")
    assert list(found["Dataset ID"]) == ["CRW_sst_v1_0_monthly"]
    assert found["Server url"].iloc[0] == server
