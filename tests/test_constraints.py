"""Tests for the ERDDAP griddap constraint parser."""

import numpy as np
import pandas as pd
import pytest

from xpublish_erddap.constraints import (
    ConstraintError,
    NoMatchError,
    parse_griddap_query,
    parse_selector,
)


@pytest.fixture
def axes():
    return {
        "time": np.array(pd.date_range("1993-01-01", periods=100, freq="D")),
        "lat": np.linspace(10.0, 80.0, 71),
        "lon": np.linspace(200.0, 250.0, 51),
    }


def test_index_form(axes):
    sel = parse_selector("0:2:10", axes["lat"])
    assert (sel.start, sel.stop, sel.stride) == (0, 10, 2)
    assert sel.size == 6


def test_shorthands(axes):
    assert parse_selector("", axes["lat"]).size == 71
    assert parse_selector("5", axes["lat"]).size == 1
    assert parse_selector("5:9", axes["lat"]).size == 5


def test_full_query(axes):
    parsed = parse_griddap_query(
        "tos[0:1:3][0:1:2][0:1:1]",
        axes,
        ["time", "lat", "lon"],
        ["tos"],
    )
    assert parsed.variables == ["tos"]
    assert parsed.selections["time"].size == 4


def test_empty_query_returns_everything(axes):
    parsed = parse_griddap_query("", axes, ["time", "lat", "lon"], ["tos", "sos"])
    assert parsed.variables == ["tos", "sos"]
    assert parsed.selections["time"].size == 100


def test_bare_axis_request(axes):
    """erddapy's griddap_initialize probes each axis with '?<dim>'."""
    parsed = parse_griddap_query("time", axes, ["time", "lat", "lon"], ["tos"])
    assert parsed.variables == ["time"]


def test_unknown_variable_rejected(axes):
    with pytest.raises(ConstraintError, match="unknown variable"):
        parse_griddap_query("nope[0]", axes, ["time", "lat", "lon"], ["tos"])


def test_mismatched_subsets_rejected(axes):
    with pytest.raises(ConstraintError, match="same subset"):
        parse_griddap_query(
            "tos[0:1:3][0][0],sos[0:1:9][0][0]",
            axes,
            ["time", "lat", "lon"],
            ["tos", "sos"],
        )


@pytest.mark.parametrize(
    ("values", "target", "expected"),
    [
        (np.array([-0.5, 0.5]), "(0.0)", 1),  # ascending: the larger value
        (np.array([0.5, -0.5]), "(0.0)", 0),  # descending: still the larger
        (np.array([-0.025, 0.025], dtype="float32"), "(0.0)", 1),
    ],
)
def test_nearest_match_ties_pick_the_larger_value(values, target, expected):
    """Issue #11: ERDDAP breaks exact ties toward the larger coordinate."""
    assert parse_selector(target, values).start == expected


def test_time_ties_pick_the_later_time():
    times = np.array(["1985-01-01T12:00", "1985-02-01T12:00"], dtype="datetime64[ns]")
    assert parse_selector("(1985-01-17T00:00:00Z)", times).start == 1


def test_axis_only_request_takes_a_selector(axes):
    parsed = parse_griddap_query(
        "time[(last)],lat[0:1:2]",
        axes,
        ["time", "lat", "lon"],
        ["tos"],
    )
    assert parsed.variables == ["time", "lat"]
    assert parsed.selections["time"].start == 99
    assert parsed.selections["lat"].stop == 2


def test_axis_only_request_refuses_a_reversed_range(axes):
    """ERDDAP swaps a reversed range for data variables, not for axes."""
    with pytest.raises(ConstraintError, match="axis order"):
        parse_griddap_query("lat[(40):1:(30)]", axes, ["time", "lat", "lon"], ["tos"])
    parsed = parse_griddap_query(
        "tos[0][(40):1:(30)][0]",
        axes,
        ["time", "lat", "lon"],
        ["tos"],
    )
    assert (parsed.selections["lat"].start, parsed.selections["lat"].stop) == (20, 30)


# --- values off an axis are refused, as ERDDAP does (#57) -------------------


def off(selector, values, **kw):
    with pytest.raises(NoMatchError) as err:
        parse_selector(selector, values, **kw)
    return str(err.value)


def test_time_axis_margin_and_wording(axes):
    # daily axis: half a day of margin
    assert parse_selector("(1993-01-01T00:00:00Z)", axes["time"]).start == 0
    assert parse_selector("(1992-12-31T12:00:00Z)", axes["time"]).start == 0
    msg = off("(1990-01-01)", axes["time"])
    assert msg.endswith(
        'Start="1990-01-01" is less than the axis minimum=1993-01-01T00:00:00Z'
        " (and even 1992-12-31T12:00:00Z).",
    )
    assert "2030-01-01" in off("(2030-01-01)", axes["time"])


def test_last_minus_d_is_checked_in_value_space(axes):
    assert "-920.0" in off("(last-1000)", axes["lat"])
    assert parse_selector("(last-10)", axes["lat"]).start == 60


def test_float32_axes_use_five_digits():
    lat = np.arange(10, dtype="float32") * np.float32(0.1)
    # 0.9 + 0.05 = 0.95; 5 digits let 0.950004 through, not 0.9501
    assert parse_selector("(0.950004)", lat).start == 9
    assert "greater than" in off("(0.9501)", lat)


def test_one_value_axis_has_its_own_margin():
    depth = np.array([0.0])
    assert parse_selector("(0.01)", depth).start == 0
    assert "greater than" in off("(0.02)", depth)


def test_descending_axis_has_the_same_range():
    lat = np.linspace(80.0, 10.0, 71)
    assert parse_selector("(80.5)", lat).start == 0
    assert "greater than" in off("(80.6)", lat)


def test_indices_are_still_indices(axes):
    # an integer index is checked against the axis length, not by value
    assert parse_selector("70", axes["lat"]).start == 70
    with pytest.raises(ConstraintError) as err:
        parse_selector("71", axes["lat"])
    assert not isinstance(err.value, NoMatchError)


def test_far_dates_do_not_wrap_into_the_axis(axes):
    # 2**64 ns after 1993-02-01: datetime64[ns] wraps it back onto the axis
    assert "greater than" in off("(2577-08-21T23:34:33)", axes["time"])
    assert "greater than" in off("(3000-01-01)", axes["time"])
    assert 'Start="1500-01-01" is less than' in off("(1500-01-01)", axes["time"])
    assert "less than" in off("(last-100000000000)", axes["time"])


def test_last_minus_fractional_seconds(axes):
    # ERDDAP keeps d a double; half a day back from the last day is a tie,
    # which goes to the larger value
    assert parse_selector("(last-43200)", axes["time"]).start == 99
    assert parse_selector("(last-43200.5)", axes["time"]).start == 98


def test_float32_margin_uses_erddaps_seven_digit_doubles():
    # erdMH1chla8day latitude: 4320 float32 values, 89.979164 down to -89.97917.
    # Live ERDDAP (2026-10-08): "... axis minimum=-89.97917 (and even -90.00000333294744)."
    lat = np.linspace(89.979164, -89.97917, 4320).astype("float32")
    lat[0], lat[-1] = np.float32(89.979164), np.float32(-89.97917)
    msg = off("(-95)", lat)
    assert "axis minimum=-89.97917 (and even -90.00000333294744)." in msg


# --- time and "last" read as ERDDAP reads them (#58) --------------------------


def test_last_plus_and_minus(axes):
    lat = axes["lat"]
    assert parse_selector("last+0", lat).start == parse_selector("last", lat).start
    assert parse_selector("last+-1", lat).start == parse_selector("last-1", lat).start
    assert parse_selector("last - 1", lat).start == 69
    assert parse_selector("(last+-10)", lat).start == 60
    assert parse_selector("(last+0.4)", lat).start == 70
    # a negative offset after "-" goes past the end: off the axis, as in ERDDAP
    assert "greater than the axis maximum=85.0" in off("(last--5)", lat)


def test_bad_last_is_a_400_with_erddaps_text(axes):
    """``(last-)`` is the one case parity lacks (it has ``last 0``, ``last-1.5``, ``(last-x)``)."""
    with pytest.raises(ConstraintError) as err:
        parse_selector("(last-)", axes["lat"], where="W")
    assert not isinstance(err.value, NoMatchError)
    assert str(err.value) == "Query error: The +/- value in Start=(last-) isn't valid."


def test_last_plus_one_is_past_the_end(axes):
    """``last+1`` is the one index case parity lacks (it has -1, 1.5, +1, 9000)."""
    with pytest.raises(ConstraintError) as err:
        parse_selector("last+1", axes["lat"], where="For variable=tos axis#1=lat")
    assert str(err.value) == (
        'Query error: For variable=tos axis#1=lat Constraint="[last+1]": '
        'Start="71" is invalid.  It must be an integer between 0 and 70.'
    )


@pytest.mark.parametrize(
    ("selector", "role", "axis"),
    [
        ("(2019:01:01)", "Start", "time"),
        ("(NaN)", "Start", "time"),
        ("(1993-01-05):(NaN)", "Stop", "time"),
        ("(20):(abc)", "Stop", "lat"),
    ],
)
def test_unreadable_values_are_a_400(axes, selector, role, axis):
    """Start is also a parity case (``(notadate)``); the Stop role is not."""
    with pytest.raises(ConstraintError) as err:
        parse_selector(selector, axes[axis], where="For variable=tos axis#1=lat")
    assert not isinstance(err.value, NoMatchError)
    assert str(err.value) == (
        f'Query error: For variable=tos axis#1=lat Constraint="[{selector}]": '
        f"{role}=NaN (invalid format?) isn't allowed."
    )


def test_iso_time_on_an_undecoded_numeric_time_axis_is_a_400():
    hours = np.arange(10.0)  # "hours since ...", left undecoded
    with pytest.raises(ConstraintError) as err:
        parse_selector("(2019-01-01)", hours)
    assert not isinstance(err.value, NoMatchError)


def test_time_axis_outside_the_nanosecond_range():
    # datetime64[s] can hold years numpy's [ns] cannot; nothing may overflow
    years = np.array(["2300-01-01", "2400-01-01", "2500-01-01"], dtype="datetime64[s]")
    assert parse_selector("(2399-12-01)", years).start == 1
    assert parse_selector("(last)", years).start == 2
    assert "greater than" in off("(2700-01-01)", years)
