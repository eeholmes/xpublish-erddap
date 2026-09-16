"""Tests for the ERDDAP griddap constraint parser."""

import numpy as np
import pandas as pd
import pytest

from xpublish_erddap.constraints import (
    ConstraintError,
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
