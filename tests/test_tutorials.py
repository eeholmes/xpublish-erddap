"""User tutorials, run unchanged against xpublish-erddap.

Each test repeats the data-access steps of a tutorial our users follow, with
only the server swapped. The datasets are stand-ins from ``tutorial_data.py``:
the real ids and axes, with formula values, so every value can be checked.

- CoastWatch satellite course, Python tutorials 1 and 3
  (coastwatch.gitbook.io/satellite-course): a hand-built griddap ``.nc`` URL
  downloaded with ``urllib``, opened with ``decode_cf=False``, times decoded
  with ``netCDF4.num2date``.
- erddapy docs, ``01a-griddap-output``: ``griddap_initialize``, strides, a
  0-360 bounding box, ``to_xarray()``.

The R tutorials are in ``test_tutorials.R``.
"""

import sys
import urllib.request

import numpy as np
import pytest
import xarray as xr
from tutorial_data import rose, sst

erddapy = pytest.importorskip("erddapy")
nc = pytest.importorskip("netCDF4")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Live server tests are unreliable on Windows Github Actions workers",
)

ORIGINAL = "https://oceanwatch.pifsc.noaa.gov/erddap"


def _download(url: str, server: str, tmp_path) -> xr.Dataset:
    """The tutorials' download-then-open steps, pointed at our server."""
    path = tmp_path / "sst.nc"
    urllib.request.urlretrieve(url.replace(ORIGINAL, server), path)  # noqa: S310
    return xr.open_dataset(path, decode_cf=False)


def _check_sst(ds: xr.Dataset) -> None:
    """Every value matches the stand-in's formula at the returned coordinates."""
    times = np.array(
        nc.num2date(ds.time.values, ds.time.units, only_use_cftime_datetimes=False),
        dtype="datetime64[ns]",
    )
    expected = sst(
        times[:, None, None],
        ds.latitude.values[None, :, None],
        ds.longitude.values[None, None, :],
    )
    np.testing.assert_allclose(ds.analysed_sst.values, expected)


def test_python_tutorial_1(xpublish_server, tmp_path):
    """CoastWatch Python tutorial 1: how to work with satellite data."""
    url = (
        "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/CRW_sst_v1_0_monthly.nc"
        "?analysed_sst[(2018-01-01T12:00:00Z):1:(2018-12-01T12:00:00Z)]"
        "[(17):1:(30)][(195):1:(210)]"
    )
    ds = _download(url, xpublish_server, tmp_path)

    # the tutorial prints this shape
    assert ds.analysed_sst.shape == (12, 261, 301)

    dates = nc.num2date(ds.time, ds.time.units)
    assert [d.strftime("%Y-%m-%d %H") for d in dates] == [
        f"2018-{m:02d}-01 12" for m in range(1, 13)
    ]

    lat_bnds, lon_bnds = [18, 23], [200, 206]
    da = ds.sel(latitude=slice(*lat_bnds), longitude=slice(*lon_bnds))
    # grid points sit at .025 offsets, so 18..23 holds 100 of them
    assert da.analysed_sst.shape == (12, 100, 120)
    _check_sst(ds)


def test_python_tutorial_3(xpublish_server, tmp_path):
    """CoastWatch Python tutorial 3: extract data within a shapefile."""
    url = (
        "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/CRW_sst_v1_0_monthly.nc"
        "?analysed_sst[(2019-01-15):1:(2019-12-15)]"
        "[(19.2345832):1:(31.79786423)][(177.84422):1:(198.9827)]"
    )
    ds = _download(url, xpublish_server, tmp_path)

    # the tutorial prints this shape
    assert ds.analysed_sst.shape == (12, 252, 424)
    # date-only times snap to the nearest monthly stamp
    dates = nc.num2date(ds.time, ds.time.units)
    assert dates[0].strftime("%Y-%m-%d") == "2019-01-01"
    assert dates[-1].strftime("%Y-%m-%d") == "2019-12-01"
    _check_sst(ds)


@pytest.fixture
def etopo(xpublish_server):
    """The erddapy example's client, pointed at our server."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap")
    e.dataset_id = "etopo5_EDDGridCopy"
    e.griddap_initialize()
    return e


def test_erddapy_griddap_example_defaults(etopo):
    """The example prints its variables and default constraints.

    These are the strings the erddapy docs show for the real server.
    """
    assert etopo.variables == ["ROSE"]
    assert etopo.constraints == {
        "latitude>=": "-90.0",
        "latitude<=": "90.0",
        "latitude_step": "1",
        "longitude>=": "0.0",
        "longitude<=": "359.91999999999996",
        "longitude_step": "1",
    }


def test_erddapy_griddap_example_download(etopo):
    """Strides of 10, then a 0-360 bounding box, then to_xarray()."""
    etopo.constraints["latitude_step"] = 10
    etopo.constraints["longitude_step"] = 10
    ds = etopo.to_xarray()
    assert ds.ROSE.shape == (217, 432)

    etopo.constraints.update(
        {
            "longitude>=": 290.908,
            "longitude<=": 340.365,
            "latitude>=": -60.533,
            "latitude<=": 0.033,
        },
    )
    ds = etopo.to_xarray()
    assert float(ds.latitude.min()) == pytest.approx(-60.5, abs=0.05)
    assert float(ds.longitude.min()) == pytest.approx(290.9, abs=0.05)
    assert ds.latitude.max() <= 0.033
    assert ds.longitude.max() <= 340.365
    np.testing.assert_allclose(
        ds.ROSE.values,
        rose(ds.latitude.values[:, None], ds.longitude.values[None, :]),
    )


@pytest.mark.xfail(
    reason="response='opendap' needs .dods, which is not served yet (#2)",
    strict=True,
)
def test_erddapy_opendap_response(etopo):
    """erddapy can also open the griddap URL itself as OPeNDAP."""
    etopo.response = "opendap"
    ds = etopo.to_xarray()
    assert ds.ROSE.shape == (2161, 4320)
    assert float(ds.ROSE[1080, 0]) == 0.0
