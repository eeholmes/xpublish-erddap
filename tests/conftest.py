"""Shared fixtures."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr


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
            "tos": (("time", "lat", "lon"), rng.random((6, 5, 4), dtype="float32"),
                    {"units": "degC", "long_name": "Sea Surface Temperature"}),
            "sos": (("time", "lat", "lon"), rng.random((6, 5, 4), dtype="float32"),
                    {"units": "psu", "long_name": "Sea Surface Salinity"}),
            "thetao": (("time", "depth", "lat", "lon"),
                       rng.random((6, 2, 5, 4), dtype="float32"),
                       {"units": "degC"}),
        },
        coords={"time": time, "lat": lat, "lon": lon, "depth": depth},
        attrs={"title": "test grid", "institution": "test"},
    )
