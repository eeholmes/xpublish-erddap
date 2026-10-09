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


@pytest.mark.parametrize("value", ["abc", "NaN", "notadate"])
def test_unreadable_value_is_a_400_like_erddap(axes, value):
    is_time = value == "notadate"
    axis, start = (axes["time"], "1993-01-05") if is_time else (axes["lat"], "20")
    selector = f"({start}):({value})"
    with pytest.raises(ConstraintError) as err:
        parse_selector(selector, axis, where="For variable=tos axis#1=lat")
    assert not isinstance(err.value, NoMatchError)
    assert str(err.value) == (
        f'Query error: For variable=tos axis#1=lat Constraint="[{selector}]": '
        "Stop=NaN (invalid format?) isn't allowed."
    )


def test_float32_margin_uses_erddaps_seven_digit_doubles():
    # erdMH1chla8day latitude: 4320 float32 values, 89.979164 down to -89.97917.
    # Live ERDDAP (2026-10-08): "... axis minimum=-89.97917 (and even -90.00000333294744)."
    lat = np.linspace(89.979164, -89.97917, 4320).astype("float32")
    lat[0], lat[-1] = np.float32(89.979164), np.float32(-89.97917)
    msg = off("(-95)", lat)
    assert "axis minimum=-89.97917 (and even -90.00000333294744)." in msg


# --- time and "last" read as ERDDAP reads them (#58) --------------------------


@pytest.fixture
def at_nine():
    """Daily at 09:00Z, like jplMURSST41: a lost time zone changes the day."""
    return np.array(pd.date_range("2013-01-01T09:00", periods=10, freq="D"))


@pytest.mark.parametrize(
    "value",
    [
        "2013-01-02T03:00:00+08:00",
        "2013-01-02T03:00:00 08:00",  # a raw "+" after URL decoding
        "2013-01-02T03:00:00+08",
        "2013-01-02T03:00:00 08",
        "2013-01-02T03:00:00+0800",
        "2013-01-02T03:00:00 0800",
    ],
)
def test_time_zone_with_raw_or_encoded_plus(at_nine, value):
    # 19:00Z on the 1st: nearest is the 1st, not the 2nd
    assert parse_selector(f"({value})", at_nine).start == 0
    assert parse_selector("(2013-01-02T03:00:00)", at_nine).start == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2013-01-32", "2013-02-01"),
        ("2013-01-05T48:00", "2013-01-07"),
        ("2013-02-00", "2013-01-31"),
    ],
)
def test_impossible_dates_roll_over(value, expected):
    days = np.array(pd.date_range("2013-01-01T09:00", periods=60, freq="D"))
    start = parse_selector(f"({value})", days).start
    assert str(days[start])[:10] == expected


def test_last_plus_and_minus(axes):
    lat = axes["lat"]
    assert parse_selector("last+0", lat).start == parse_selector("last", lat).start
    assert parse_selector("last+-1", lat).start == parse_selector("last-1", lat).start
    assert parse_selector("last - 1", lat).start == 69
    assert parse_selector("(last+-10)", lat).start == 60
    assert parse_selector("(last+0.4)", lat).start == 70
    # a negative offset after "-" goes past the end: off the axis, as in ERDDAP
    assert "greater than the axis maximum=85.0" in off("(last--5)", lat)


@pytest.mark.parametrize(
    ("selector", "message"),
    [
        ("last 0", 'Query error: Unexpected character after "last" in Start=last 0.'),
        (
            "last-1.5",
            "Query error: The +/- index value in Start=last-1.5 isn't an integer.\n"
            '(Cause: java.lang.NumberFormatException: For input string: "1.5")',
        ),
        ("(last-x)", "Query error: The +/- value in Start=(last-x) isn't valid."),
        ("(last-)", "Query error: The +/- value in Start=(last-) isn't valid."),
    ],
)
def test_bad_last_is_a_400_with_erddaps_text(axes, selector, message):
    with pytest.raises(ConstraintError) as err:
        parse_selector(selector, axes["lat"], where="W")
    assert not isinstance(err.value, NoMatchError)
    assert str(err.value) == message


@pytest.mark.parametrize(
    ("selector", "message"),
    [
        ("-1", 'Start="-1" is invalid.'),
        ("0:1:-1", 'Stop="-1" is invalid.'),
        ("1.5", 'Start="1.5" is invalid.'),
        ("+1", 'Start="+1" is invalid.'),
        ("71", 'Start="71" is invalid.'),
        ("last-71", 'Start="-1" is invalid.'),
        ("last+1", 'Start="71" is invalid.'),
    ],
)
def test_indices_are_digits_within_the_axis(axes, selector, message):
    with pytest.raises(ConstraintError) as err:
        parse_selector(selector, axes["lat"], where="For variable=tos axis#1=lat")
    assert str(err.value) == (
        f'Query error: For variable=tos axis#1=lat Constraint="[{selector}]": '
        f"{message}  It must be an integer between 0 and 70."
    )


@pytest.mark.parametrize("value", ["notadate", "1_500_000_000", "2019:01:01", "NaN"])
def test_unreadable_times_are_a_400(axes, value):
    with pytest.raises(ConstraintError) as err:
        parse_selector(f"({value})", axes["time"])
    assert "NaN (invalid format?) isn't allowed." in str(err.value)


@pytest.mark.parametrize(
    ("selector", "role"),
    [("()", "Start"), ("(  ):1:(5)", "Start"), ("0:1:()", "Stop")],
)
def test_empty_parentheses_are_missing_values(axes, selector, role):
    """``EDDGrid.parseAxisBrackets``, checked on erddap.ioos.us etopo5: ``[()]``."""
    with pytest.raises(ConstraintError) as err:
        parse_selector(selector, axes["lat"], where="For variable=tos axis#1=lat")
    assert str(err.value).endswith(f": The {role} value inside () is missing.")


def test_epoch_seconds_and_numbers_on_a_time_axis(axes):
    first = pd.Timestamp("1993-01-01").timestamp()
    assert parse_selector(f"({first + 86400:.0f})", axes["time"]).start == 1
    assert parse_selector(f"({first + 86400:.4e})", axes["time"]).start == 1


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
