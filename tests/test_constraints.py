"""Tests for the ERDDAP griddap constraint parser."""

import numpy as np
import pandas as pd
import pytest

from xpublish_erddap.constraints import (
    ConstraintError,
    NoMatchError,
    parse_griddap_query,
    parse_selector,
    split_selectors,
)


@pytest.fixture
def axes():
    return {
        "time": np.array(pd.date_range("1993-01-01", periods=100, freq="D")),
        "lat": np.linspace(10.0, 80.0, 71),
        "lon": np.linspace(200.0, 250.0, 51),
    }


def test_split_selectors():
    assert split_selectors("tos[0:1:2][3]") == ("tos", ["0:1:2", "3"])
    assert split_selectors("tos") == ("tos", [])


def test_iso_times_are_not_split_on_their_colons(axes):
    sel = parse_selector(
        "(1993-01-05T00:00:00Z):1:(1993-01-09T00:00:00Z)",
        axes["time"],
    )
    assert (sel.start, sel.stop, sel.stride) == (4, 8, 1)


def test_index_form(axes):
    sel = parse_selector("0:2:10", axes["lat"])
    assert (sel.start, sel.stop, sel.stride) == (0, 10, 2)
    assert sel.size == 6


def test_shorthands(axes):
    assert parse_selector("", axes["lat"]).size == 71
    assert parse_selector("5", axes["lat"]).size == 1
    assert parse_selector("5:9", axes["lat"]).size == 5


def test_last_forms(axes):
    n = len(axes["lat"])
    assert parse_selector("last", axes["lat"]).start == n - 1
    assert parse_selector("last-3", axes["lat"]).start == n - 4
    assert parse_selector("(last)", axes["lat"]).start == n - 1


def test_coordinate_values_use_nearest(axes):
    # 20.3 is not an exact grid point
    sel = parse_selector("(20.3)", axes["lat"])
    assert abs(axes["lat"][sel.start] - 20.3) <= 0.5


def test_reversed_range_is_tolerated(axes):
    """erddapy emits min>max for descending axes; ERDDAP copes, so must we."""
    sel = parse_selector("(30.0):1:(20.0)", axes["lat"])
    assert sel.start < sel.stop


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


def test_wrong_selector_count_rejected(axes):
    with pytest.raises(ConstraintError, match="expects 3 selectors"):
        parse_griddap_query("tos[0][0]", axes, ["time", "lat", "lon"], ["tos"])


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


def test_value_beyond_the_half_spacing_margin_is_refused(axes):
    # lat runs 10..80 in steps of 1: the margin is 0.5 each side
    assert parse_selector("(80.5)", axes["lat"]).start == 70
    assert parse_selector("(9.5)", axes["lat"]).start == 0
    assert "greater than the axis maximum" in off("(80.51)", axes["lat"])
    assert "less than the axis minimum=10.0 (and even 9.5)" in off("(9.49)", axes["lat"])


def test_start_and_stop_are_both_checked(axes):
    assert off("(20):(95)", axes["lat"]).count('"Stop"') == 1
    assert 'Start="-5"' in off("(-5):(20)", axes["lat"])


def test_wrong_longitude_convention_is_refused(axes):
    assert "less than the axis minimum" in off("(-130):1:(-120)", axes["lon"])


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


def test_error_names_the_variable_and_constraint(axes):
    with pytest.raises(NoMatchError) as err:
        parse_griddap_query(
            "tos[(1993-01-02)][(45):1:(99)][0]",
            axes,
            ["time", "lat", "lon"],
            ["tos"],
        )
    assert str(err.value).startswith(
        "Your query produced no matching results. Query error: "
        'For variable=tos axis#1=lat Constraint="[(45):1:(99)]": ',
    )
    with pytest.raises(NoMatchError) as err:
        parse_griddap_query("lon[(300)]", axes, ["time", "lat", "lon"], ["tos"])
    assert 'For variable=lon axis#2=lon Constraint="[(300)]"' in str(err.value)
