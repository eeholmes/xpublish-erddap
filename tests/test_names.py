"""ERDDAP's variable names: latitude/longitude/time axes and safe names (#59)."""

import io

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin
from xpublish_erddap.catalog import (
    build_catalog,
    is_variable_name_safe,
    recognised_axis,
    safe_variable_name,
)

DIMS = ("t", "lat", "lon")


def short_names() -> xr.Dataset:
    """A store with the axis names many Zarr stores use: ``t``, ``lat``, ``lon``."""
    return xr.Dataset(
        {
            "sst": (
                ("t", "lat", "lon"),
                np.arange(24, dtype="float32").reshape(2, 3, 4),
                {"units": "degC"},
            ),
            "sst-anom": (
                ("t", "lat", "lon"),
                np.zeros((2, 3, 4), dtype="float32"),
                {"units": "degC"},
            ),
        },
        coords={
            "t": pd.date_range("2020-01-01", periods=2, freq="D"),
            "lat": ("lat", [10.0, 20.0, 30.0], {"units": "degrees_north"}),
            "lon": ("lon", [100.0, 110.0, 120.0, 130.0], {"units": "degrees_east"}),
        },
        attrs={"title": "short names"},
    )


def client_for(ds: xr.Dataset, **options) -> TestClient:
    rest = xpublish.Rest({"short": ds}, plugins={"erddap": ErddapPlugin(**options)})
    return TestClient(rest.app)


@pytest.fixture(scope="module")
def client():
    return client_for(short_names())


SERVED = ["time", "latitude", "longitude"]


def test_dds_uses_erddap_names(client):
    body = client.get("/erddap/griddap/short.dds").text
    for name in SERVED:
        assert f"{name}[{name} = " in body
    assert "lat[" not in body
    assert " t[" not in body


def test_info_uses_erddap_names(client):
    df = pd.read_csv(io.StringIO(client.get("/erddap/info/short/index.csv").text))
    dims = df[df["Row Type"] == "dimension"]["Variable Name"].tolist()
    assert dims == SERVED
    assert set(df[df["Row Type"] == "variable"]["Variable Name"]) == {"sst", "sst_anom"}


def test_csv_header_and_constraints_use_erddap_names(client):
    body = client.get(
        "/erddap/griddap/short.csvp?sst[(2020-01-02)][(15):(30)][(110)]",
    ).text
    df = pd.read_csv(io.StringIO(body))
    assert list(df.columns) == [
        "time (UTC)",
        "latitude (degrees_north)",
        "longitude (degrees_east)",
        "sst (degC)",
    ]
    assert df["sst (degC)"].tolist() == [17.0, 21.0]


def test_source_names_are_unknown_variables(client):
    resp = client.get("/erddap/griddap/short.csv?lat[0]")
    assert resp.status_code == 400
    assert "lat" in resp.text


def test_unsafe_variable_name_is_served_under_erddaps_safe_name(client):
    """``sst-anom`` was listed but unreachable: ``?sst-anom`` reads as ``sst``."""
    assert "sst_anom" in client.get("/erddap/griddap/short.dds").text
    resp = client.get("/erddap/griddap/short.csv?sst_anom[0][0][0]")
    assert resp.status_code == 200
    assert resp.text.splitlines()[0] == "time,latitude,longitude,sst_anom"


def test_dataset_id_comes_from_source_names():
    """Renaming must not move a split dataset's id: it keeps the source suffix."""
    ds = short_names()
    ds["deep"] = (("t", "z", "lat", "lon"), np.zeros((2, 1, 3, 4)))
    ds = ds.assign_coords(z=[5.0])
    on = {e.dataset_id for e in build_catalog("s", ds)}
    off = {e.dataset_id for e in build_catalog("s", ds, rename_axes=False)}
    assert on == off == {"s", "s_z"}


def test_option_off_keeps_source_names():
    body = client_for(short_names(), rename_axes=False).get("/erddap/griddap/short.dds").text
    assert "t[t = 2]" in body
    assert "lat[lat = 3]" in body
    # names ERDDAP cannot serve are made safe either way
    assert "sst_anom" in body


def test_mapping_replaces_recognition():
    (entry,) = build_catalog("s", short_names(), rename_axes={"lon": "x_deg"})
    assert entry.dims == ("t", "lat", "x_deg")
    assert entry.data_vars == ("sst", "sst_anom")


def test_target_name_taken_leaves_the_axis_alone(caplog):
    ds = short_names()
    ds["latitude"] = (("t", "lat", "lon"), np.zeros((2, 3, 4)))
    (entry,) = build_catalog("s", ds)
    assert entry.dims == ("time", "lat", "longitude")
    assert "latitude" in entry.data_vars
    assert "'lat'" in caplog.text
    assert "taken" in caplog.text


def test_unsafe_name_that_clashes_is_left_out(caplog):
    ds = short_names()
    ds["sst_anom"] = ds["sst-anom"]
    (entry,) = build_catalog("s", ds)
    assert entry.data_vars == ("sst", "sst_anom")
    assert "leaving out variable 'sst-anom'" in caplog.text


def da(values, **attrs) -> xr.DataArray:
    return xr.DataArray(np.asarray(values), attrs=attrs)


@pytest.mark.parametrize(
    ("name", "array", "expected"),
    [
        ("lat", da([1.0, 2.0], units="degrees_north"), "latitude"),
        ("lat", da([1.0, 2.0]), "latitude"),  # ERDDAP: a lat name with no units
        ("latitude", da([1.0, 2.0], units="degrees"), "latitude"),
        ("j", da([1.0, 2.0], units="degrees_north"), "latitude"),
        ("j", da([1.0, 2.0], standard_name="latitude"), "latitude"),
        ("lon", da([1.0, 2.0], units="degrees_east"), "longitude"),
        ("long", da([1.0, 2.0], units="degrees"), "longitude"),
        ("x", da([1.0, 2.0], units="degree_east"), "longitude"),
        ("t", da(pd.date_range("2020", periods=2).values), "time"),
        # projected axes are not lat/lon (#60)
        ("x", da([1.0, 2.0], units="m"), None),
        ("y", da([1.0, 2.0], standard_name="projection_y_coordinate"), None),
        # a rotated grid's degrees are not latitude
        ("grid_latitude", da([1.0, 2.0], units="degrees", standard_name="grid_latitude"), None),
        ("rlat", da([1.0, 2.0], units="degrees"), None),
        ("lat", da([1.0, 2.0], units="degrees_east"), None),
        ("latin_name", da([1.0, 2.0]), None),
        # a forecast lead is not time, nor is undecoded CF time
        ("lead_time", da(np.array([0, 6], dtype="timedelta64[h]")), None),
        ("t", da([0.0, 1.0], units="days since 2000-01-01"), None),
        ("depth", da([0.0, 10.0], units="m"), None),
    ],
)
def test_recognised_axis(name, array, expected):
    assert recognised_axis(name, array) == expected


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("sst", "sst"),
        ("_sst", "_sst"),
        ("sst-anom", "sst_anom"),
        ("1st", "a_1st"),
        ("sea surface temp.", "sea_surface_temp"),
        ("a--b", "a_b"),
        ("-", "a"),
    ],
)
def test_safe_variable_name(name, safe):
    assert is_variable_name_safe(safe)
    if name == safe:
        assert is_variable_name_safe(name)
    else:
        assert not is_variable_name_safe(name)
        assert safe_variable_name(name) == safe
