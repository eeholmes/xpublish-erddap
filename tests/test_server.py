"""Test real ERDDAP clients against the Xpublish ERDDAP plugin.

These run against a live server over a socket, because the whole point of the
package is that unmodified `erddapy` (and `rerddap`) code works. The
`TestClient` suite in `test_api.py` cannot catch problems that only appear with
a real HTTP client -- content-type handling and percent-encoding among them.
"""

import sys

import numpy as np
import pytest

erddapy = pytest.importorskip("erddapy")

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
    assert erddap.dim_names == ["time", "lat", "lon"]
    assert erddap.variables == ["air"]
    for dim in ("time", "lat", "lon"):
        assert f"{dim}>=" in erddap.constraints
        assert f"{dim}_step" in erddap.constraints


def test_to_xarray_with_coordinate_constraints(erddap, dataset):
    """A coordinate-value subset round-trips into an xarray Dataset."""
    erddap.constraints.update(
        {
            "time>=": "2013-01-05T00:00:00Z",
            "time<=": "2013-01-08T00:00:00Z",
            "lat>=": 40.0,
            "lat<=": 50.0,
            "lon>=": 240.0,
            "lon<=": 250.0,
        },
    )
    ds = erddap.to_xarray()

    assert set(ds.sizes) == {"time", "lat", "lon"}
    assert ds.time.size == 13
    assert ds.lat.max() <= 50.0
    assert ds.lat.min() >= 40.0

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
        {"lat>=": 45.0, "lat<=": 47.5, "lon>=": 240.0, "lon<=": 242.5},
    )
    df = erddap.to_pandas()

    assert list(df.columns) == [
        "time (UTC)",
        "lat (degrees_north)",
        "lon (degrees_east)",
        "air (degK)",
    ]
    assert len(df) > 0


def test_mixed_dimensions_split_into_two_datasets(xpublish_server):
    """A source whose variables differ in dimensions becomes several datasets."""
    import httpx

    body = httpx.get(f"{xpublish_server}/griddap/index.csv", timeout=30).text
    assert "mixed" in body
    assert "mixed_level" in body


def test_griddap_initialize_on_the_split_dataset(xpublish_server):
    """The extra hypercube is usable, not just listed."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap", response="nc")
    e.dataset_id = "mixed_level"
    # expand_dims puts the new dimension first, and the catalog preserves
    # the source's dimension order
    assert e.dim_names == ["level", "time", "lat", "lon"]
    assert e.variables == ["air_levels"]
