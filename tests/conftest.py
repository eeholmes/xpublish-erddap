"""Py.test configuration and shared fixtures."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from xarray.tutorial import open_dataset
from xprocess import ProcessStarter

server_path = Path(__file__).parent / "server.py"


@pytest.fixture
def xpublish_server(xprocess):
    """Launch an Xpublish server in the background.

    Serves the air_temperature tutorial dataset with the ERDDAP plugin
    running with defaults, so real clients can be exercised over a socket.
    """

    class Starter(ProcessStarter):
        # Wait till the pattern is printed before considering things started
        pattern = "Uvicorn running on"

        # server startup args
        args = ["python", str(server_path)]

        # seconds before timing out on server startup
        timeout = 60

        # Try to cleanup if interrupted
        terminate_on_interrupt = True

    xprocess.ensure("xpublish-erddap", Starter)
    yield "http://0.0.0.0:9000/erddap"
    xprocess.getinfo("xpublish-erddap").terminate()


@pytest.fixture(scope="session")
def dataset():
    """Xarray air temperature tutorial dataset."""
    return open_dataset("air_temperature")


@pytest.fixture(scope="session")
def grid_dataset() -> xr.Dataset:
    """A small dataset with two dimension signatures."""
    rng = np.random.default_rng(0)
    time = pd.date_range("2020-01-01", periods=6, freq="D")
    lat = np.linspace(40.0, 50.0, 5)
    lon = np.linspace(230.0, 240.0, 4)
    depth = np.array([0.0, 10.0])
    return xr.Dataset(
        {
            "tos": (
                ("time", "lat", "lon"),
                rng.random((6, 5, 4), dtype="float32"),
                {"units": "degC", "long_name": "Sea Surface Temperature"},
            ),
            "sos": (
                ("time", "lat", "lon"),
                rng.random((6, 5, 4), dtype="float32"),
                {"units": "psu", "long_name": "Sea Surface Salinity"},
            ),
            "thetao": (
                ("time", "depth", "lat", "lon"),
                rng.random((6, 2, 5, 4), dtype="float32"),
                {"units": "degC"},
            ),
        },
        coords={"time": time, "lat": lat, "lon": lon, "depth": depth},
        attrs={"title": "test grid", "institution": "test"},
    )
