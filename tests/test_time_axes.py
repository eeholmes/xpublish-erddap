"""Model calendars, lead times and projected grids, served as ERDDAP would (#60).

ERDDAP accepts time only as Gregorian seconds since 1970 and never reads
``calendar``; we serve a cftime axis as an ERDDAP admin would have converted
it, a timedelta axis as numbers in its units, and do not take projected
``x``/``y`` in metres for longitude and latitude.
"""

import io
from datetime import timedelta

import numpy as np
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin
from xpublish_erddap.catalog import build_catalog
from xpublish_erddap.timeaxes import cftime_to_datetime64

pytest.importorskip("cftime")


def model_run(calendar: str, n: int, *, units: str = "days since 1993-01-01") -> xr.Dataset:
    """A daily model run in ``calendar``, decoded as a default open decodes it."""
    raw = xr.Dataset(
        {
            "sst": (
                ("time", "lat", "lon"),
                np.arange(n * 4, dtype="float32").reshape(n, 2, 2),
            ),
        },
        coords={
            "time": (
                "time",
                np.arange(n, dtype="float64"),
                {"units": units, "calendar": calendar, "standard_name": "time"},
            ),
            "lat": ("lat", [10.0, 20.0], {"units": "degrees_north"}),
            "lon": ("lon", [100.0, 110.0], {"units": "degrees_east"}),
        },
    )
    return xr.decode_cf(raw)


def forecast() -> xr.Dataset:
    raw = xr.Dataset(
        {"v": (("lead_time", "lat"), np.arange(8, dtype="float32").reshape(4, 2))},
        coords={
            "lead_time": (
                "lead_time",
                np.array([0, 3, 6, 9], dtype="int32"),
                {"units": "hours", "long_name": "forecast lead time"},
            ),
            "lat": ("lat", [1.0, 2.0], {"units": "degrees_north"}),
        },
    )
    return xr.decode_cf(raw)


def polar() -> xr.Dataset:
    """A polar-stereographic grid: ``x``/``y`` in metres, no lat/lon axes."""
    metres = [-5e6, 0.0, 5e6]
    return xr.Dataset(
        {"ice": (("y", "x"), np.ones((3, 3), dtype="float32"))},
        coords={
            "y": ("y", metres, {"units": "m", "standard_name": "projection_y_coordinate"}),
            "x": ("x", metres, {"units": "m", "standard_name": "projection_x_coordinate"}),
        },
        attrs={"title": "polar", "geospatial_lat_min": 40.0, "time_coverage_start": "2000"},
    )


@pytest.fixture(scope="module")
def client():
    datasets = {
        "noleap": model_run("noleap", 400),
        "d360": model_run("360_day", 730),
        "lead": forecast(),
        "polar": polar(),
    }
    rest = xpublish.Rest(datasets, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


# -- cftime ---------------------------------------------------------------------
def test_noleap_keeps_its_date_labels(client):
    # day 365 of a noleap run starting 1993 is 1994-01-01 (a Gregorian
    # reading, as real ERDDAP's, would say 1993-12-31... and drift from there)
    r = client.get("/erddap/griddap/noleap.csv?time[(1993-12-31):1:(1994-01-02)]")
    assert r.status_code == 200, r.text
    assert r.text.splitlines()[2:] == [
        "1993-12-31T00:00:00Z",
        "1994-01-01T00:00:00Z",
        "1994-01-02T00:00:00Z",
    ]


def test_noleap_data_request_finds_the_right_step(client):
    r = client.get("/erddap/griddap/noleap.csv?sst[(1994-01-01)][0][0]")
    assert r.status_code == 200, r.text
    assert r.text.splitlines()[2].split(",")[-1] == str(365 * 4.0)


def test_converted_axis_drops_calendar_and_says_so(client):
    das = client.get("/erddap/griddap/noleap.das").text
    time_block = das.split("time {")[1].split("}")[0]
    assert "String calendar" not in time_block
    assert 'units "seconds since 1970-01-01T00:00:00Z"' in time_block
    assert "Converted from the 'noleap' calendar" in time_block
    assert 'time_coverage_end "1994-02-04T00:00:00Z"' in das


def test_noleap_nc_round_trips_as_gregorian(client):
    r = client.get("/erddap/griddap/noleap.nc?sst[364:1:365][0][0]")
    assert r.status_code == 200, r.text
    ds = xr.open_dataset(io.BytesIO(r.content))
    assert "calendar" not in ds.time.attrs
    assert ds.time.encoding.get("calendar") in (None, "standard", "proleptic_gregorian")
    assert [str(t)[:10] for t in ds.time.values] == ["1993-12-31", "1994-01-01"]


def test_daily_360_day_is_refused(client, caplog):
    # 1993-02-29 and 02-30 are not dates: serving them would change a time
    assert client.get("/erddap/griddap/d360.das").status_code == 404
    assert "d360" not in client.get("/erddap/griddap/index.csv").text
    assert build_catalog("d360", model_run("360_day", 730)) == []
    assert "1993-02-29 is not a Gregorian date" in caplog.text


@pytest.mark.parametrize("calendar", ["360_day", "all_leap", "366_day"])
def test_dates_that_do_not_exist_are_refused(calendar):
    times = xr.date_range("2001-02-27", periods=3, freq="D", calendar=calendar, use_cftime=True)
    with pytest.raises(ValueError, match="2001-02-29 is not a Gregorian date"):
        cftime_to_datetime64(times.values)


def test_monthly_360_day_keeps_labels():
    times = xr.date_range("2001-01-01", periods=24, freq="MS", calendar="360_day", use_cftime=True)
    times = np.array([t.replace(day=16) for t in times.values])
    served, how = cftime_to_datetime64(times)
    assert how == "each date label kept"
    assert str(served[1])[:10] == "2001-02-16"


def test_julian_is_converted_by_moment():
    # the same day, written on the Gregorian calendar (12 days later in 1900)
    times = xr.date_range("1900-01-01", periods=3, freq="D", calendar="julian", use_cftime=True)
    served, how = cftime_to_datetime64(times.values)
    assert how == "each moment kept"
    assert str(served[0])[:10] == "1900-01-13"


def test_standard_calendar_crosses_1582_by_moment():
    # the standard (mixed) calendar goes from Julian 1582-10-04 straight to
    # Gregorian 1582-10-15, one day later; both are served as Gregorian
    times = xr.date_range("1582-10-03", periods=3, freq="D", calendar="standard", use_cftime=True)
    served, _ = cftime_to_datetime64(times.values)
    assert [str(t)[:10] for t in served] == ["1582-10-13", "1582-10-14", "1582-10-15"]


MODEL_CALENDARS = ["noleap", "365_day", "360_day", "all_leap", "366_day"]
REAL_CALENDARS = ["julian", "standard", "gregorian", "proleptic_gregorian"]


def source_axes(calendar):
    """Hourly, daily and monthly axes in ``calendar`` that a step could move in."""
    for start, freq, n in (
        ("2000-02-20T00:00:00", "7h", 200),
        ("1999-12-25", "D", 400),
        ("1500-01-01", "D", 40),
        ("1990-01-16T12:00:00", "MS", 48),
    ):
        times = xr.date_range(start, periods=n, freq=freq, calendar=calendar, use_cftime=True)
        if freq == "MS":
            times = [t.replace(day=16, hour=12) for t in times]
        yield np.array(list(times), dtype=object)


@pytest.mark.parametrize("calendar", MODEL_CALENDARS + REAL_CALENDARS)
def test_no_served_time_differs_from_its_source(calendar):
    """The guarantee (EH): a format or calendar may change, a time may not.

    A model calendar has only labels, so each served label must be the
    source's, to the microsecond. A real calendar has moments: the elapsed
    time between any two steps must be the source's, and one anchor must be
    the known Gregorian date. Axes with a non-date are refused, not moved.
    """
    for values in source_axes(calendar):
        try:
            served, _ = cftime_to_datetime64(values)
        except ValueError:
            assert calendar in ("360_day", "all_leap", "366_day")
            continue
        assert served.dtype == np.dtype("datetime64[us]")
        if calendar in MODEL_CALENDARS:
            labels = [d.strftime("%Y-%m-%dT%H:%M:%S") + f".{d.microsecond:06d}" for d in values]
            assert [str(t) for t in served] == labels
            continue
        us = timedelta(microseconds=1)
        elapsed = [(b - a) // us for a, b in zip(values[:-1], values[1:], strict=True)]
        np.testing.assert_array_equal(np.diff(served).astype("int64"), elapsed)
        anchor = values[0].change_calendar("proleptic_gregorian")
        assert str(served[0])[:19] == anchor.strftime("%Y-%m-%dT%H:%M:%S")


def test_cftime_far_outside_nanoseconds():
    # datetime64[ns] ends in 2262; the served axis is in microseconds
    ds = model_run("noleap", 3, units="days since 2500-01-01")
    (entry,) = build_catalog("s", ds)
    assert str(entry.ds.time.values[0])[:10] == "2500-01-01"
    assert entry.globals_["time_coverage_start"] == "2500-01-01T00:00:00Z"


# -- timedelta --------------------------------------------------------------------
def test_lead_time_is_numbers_in_its_units(client):
    das = client.get("/erddap/griddap/lead.das").text
    block = das.split("lead_time {")[1].split("}")[0]
    assert "Int32 actual_range 0, 9;" in block
    assert 'units "hours"' in block


def test_lead_time_value_request_finds_the_right_step(client):
    # used to return lead 0: (10800) was read against nanoseconds
    r = client.get("/erddap/griddap/lead.csv?v[(3)][0]")
    assert r.status_code == 200, r.text
    assert r.text.splitlines()[2] == "3,1.0,2.0"


def test_lead_time_nc(client):
    # used to be a 500: "Key 'units' already exists"
    r = client.get("/erddap/griddap/lead.nc?v[(3):1:(6)][0]")
    assert r.status_code == 200, r.text
    ds = xr.open_dataset(io.BytesIO(r.content), decode_timedelta=False)
    assert ds.lead_time.values.tolist() == [3, 6]
    assert ds.lead_time.attrs["units"] == "hours"


# -- projected x/y ----------------------------------------------------------------
def test_projected_xy_are_not_lat_lon(client):
    das = client.get("/erddap/griddap/polar.das").text
    assert "degrees_north" not in das
    assert "geospatial_lat" not in das
    assert "geospatial_lon" not in das
    assert 'units "m"' in das


def test_supplied_bounds_go_like_erddap(client):
    # EDDGrid removes these and derives them from the axes, even when
    # supplied; with no latitude or time axis there are none
    das = client.get("/erddap/griddap/polar.das").text
    assert "geospatial_lat_min" not in das
    assert "time_coverage_start" not in das


def test_projected_grid_not_found_by_latitude(client):
    r = client.get("/erddap/search/advanced.csv?searchFor=all&minLat=30&maxLat=50")
    assert "polar" not in r.text


def test_metadata_cannot_override_derived_bounds():
    entry = build_catalog("s", model_run("noleap", 3), metadata={"geospatial_lat_min": -90.0})[0]
    assert entry.globals_["geospatial_lat_min"] == 10.0


def test_dimension_without_coordinate_is_not_degrees():
    ds = xr.Dataset({"v": (("y", "x"), np.ones((2, 2)))})
    (entry,) = build_catalog("s", ds)
    assert entry.variable_attrs("y")["units"] == "1"
    assert "geospatial_lat_min" not in entry.globals_


def test_year_before_1_is_refused(caplog):
    # no Gregorian date to give, so refused with a log line, not a 500
    ds = model_run("noleap", 3, units="days since 0000-01-01")
    assert build_catalog("s", ds) == []
    assert "no Gregorian equivalent" in caplog.text
