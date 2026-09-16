"""Stand-ins for the ERDDAP datasets that user tutorials request.

Each dataset has the real one's id, axes, dtypes and key metadata, so tutorial
URLs work verbatim. The axes are the real ones, read from the parity
snapshots in ``parity/golden`` (the CRW time axis is irregular: 35 months are
not stamped on the 1st). Data values come from a formula, computed only for the
cells a request reads (like a lazily opened remote store), so the full grids
never exist in memory and tests can check every value they get back.

- ``CRW_sst_v1_0_monthly`` -- the CoastWatch satellite-course dataset
  (oceanwatch.pifsc.noaa.gov): monthly, times mostly on the 1st at 12:00, ascending
  latitude, 0-360 longitude, float32 axes, float64 SST in degree_C.
- ``etopo5_EDDGridCopy`` -- the erddapy griddap example (erddap.ioos.us):
  no time axis, float64 axes, float32 ``ROSE`` in meters.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr
from xarray.backends import BackendArray
from xarray.core import indexing

GOLDEN = Path(__file__).parent / "parity" / "golden"


def real_axes(slug: str) -> dict[str, np.ndarray]:
    """The real dataset's axis values, from its parity snapshot."""
    with xr.open_dataset(GOLDEN / slug / "snapshot.nc") as snap:
        return {d: snap[d].values for d in snap.dims if not d.startswith("__")}


def sst(time: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """SST in degree_C for broadcastable time (datetime64), lat and lon."""
    month = time.astype("datetime64[M]").astype("int64") % 12
    return (
        28.0
        - 20.0 * (np.asarray(lat, "float64") / 90.0) ** 2
        + np.cos(2 * np.pi * month / 12.0)
        + 0.01 * np.asarray(lon, "float64")
    )


def rose(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Elevation in meters for broadcastable lat and lon."""
    return (
        1000.0 * np.sin(np.radians(np.asarray(lat, "float64")) * 3)
        + np.asarray(lon, "float64")
    ).round()


class FormulaArray(BackendArray):
    """A lazy array whose values are ``formula(*axis_values)``."""

    def __init__(self, axes: list[np.ndarray], dtype, formula):
        """Keep the axes; nothing is computed until indexed."""
        self.axes = axes
        self.shape = tuple(len(a) for a in axes)
        self.dtype = np.dtype(dtype)
        self.formula = formula

    def __getitem__(self, key):
        """Index lazily, like a real backend."""
        return indexing.explicit_indexing_adapter(
            key,
            self.shape,
            indexing.IndexingSupport.BASIC,
            self._getitem,
        )

    def _getitem(self, key: tuple) -> np.ndarray:
        picked = [np.atleast_1d(a[k]) for a, k in zip(self.axes, key, strict=True)]
        grids = np.meshgrid(*picked, indexing="ij")
        out = self.formula(*grids).astype(self.dtype)
        scalar_axes = tuple(
            i for i, k in enumerate(key) if isinstance(k, int | np.integer)
        )
        return out.squeeze(axis=scalar_axes) if scalar_axes else out


def _lazy(dims, axes, dtype, formula, attrs) -> xr.Variable:
    array = FormulaArray(axes, dtype, formula)
    return xr.Variable(dims, indexing.LazilyIndexedArray(array), attrs)


def crw_sst_v1_0_monthly() -> xr.Dataset:
    """Stand-in for oceanwatch's ``CRW_sst_v1_0_monthly``."""
    axes = real_axes("oceanwatch.pifsc.noaa.gov__CRW_sst_v1_0_monthly")
    time, lat, lon = axes["time"], axes["latitude"], axes["longitude"]
    ds = xr.Dataset(
        {
            "analysed_sst": _lazy(
                ("time", "latitude", "longitude"),
                [time, lat, lon],
                "float64",
                sst,
                {
                    "long_name": "analysed sea surface temperature",
                    "standard_name": "sea_surface_temperature",
                    "units": "degree_C",
                    "valid_min": -200.0,
                    "valid_max": 5000.0,
                },
            ),
        },
        coords={
            "time": ("time", time, {"long_name": "Centered Time", "axis": "T"}),
            "latitude": (
                "latitude",
                lat,
                {"units": "degrees_north", "standard_name": "latitude", "axis": "Y"},
            ),
            "longitude": (
                "longitude",
                lon,
                {"units": "degrees_east", "standard_name": "longitude", "axis": "X"},
            ),
        },
        attrs={
            "title": "Sea Surface Temperature, Coral Reef Watch, CoralTemp - Monthly "
            "(test stand-in)",
            "summary": "Formula values on the CRW_sst_v1_0_monthly grid.",
            "institution": "xpublish-erddap tests",
            "infoUrl": "https://oceanwatch.pifsc.noaa.gov/erddap/info/CRW_sst_v1_0_monthly/index.html",
            "license": "[standard]",
            "Conventions": "CF-1.6, ACDD-1.3, COARDS",
            "cdm_data_type": "Grid",
        },
    )
    ds["analysed_sst"].encoding["_FillValue"] = np.nan
    return ds


def etopo5_eddgridcopy() -> xr.Dataset:
    """Stand-in for erddap.ioos.us's ``etopo5_EDDGridCopy``."""
    axes = real_axes("erddap.ioos.us__etopo5_EDDGridCopy")
    lat, lon = axes["latitude"], axes["longitude"]
    return xr.Dataset(
        {
            "ROSE": _lazy(
                ("latitude", "longitude"),
                [lat, lon],
                "float32",
                rose,
                {"long_name": "Relief of the Surface of the Earth", "units": "meters"},
            ),
        },
        coords={
            "latitude": ("latitude", lat, {"units": "degrees_north"}),
            "longitude": ("longitude", lon, {"units": "degrees_east"}),
        },
        attrs={
            "title": "ETOPO5 5-minute relief (test stand-in)",
            "summary": "Formula values on the etopo5_EDDGridCopy grid.",
            "institution": "xpublish-erddap tests",
            "infoUrl": "https://erddap.ioos.us/erddap/info/etopo5_EDDGridCopy/index.html",
            "license": "[standard]",
        },
    )


def tutorial_datasets() -> dict[str, xr.Dataset]:
    """Every stand-in, keyed by its real ERDDAP datasetID."""
    return {
        "CRW_sst_v1_0_monthly": crw_sst_v1_0_monthly(),
        "etopo5_EDDGridCopy": etopo5_eddgridcopy(),
    }
