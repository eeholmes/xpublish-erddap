"""ERDDAP's number, type and spacing formats, with values seen on real servers."""

import numpy as np
import pandas as pd
import pytest

from xpublish_erddap.catalog import nice_doubles
from xpublish_erddap.formats import _duration, _spacing, attr_type, java_number


@pytest.mark.parametrize(
    ("value", "java", "das"),
    [
        (473428800.0, "4.734288E8", "4.734288e+8"),
        (np.float32(-1e34), "-1.0E34", "-1.0e+34"),
        (0.049999999999999996, "0.049999999999999996", "0.049999999999999996"),
        (np.float32(89.975), "89.975", "89.975"),
        (32.0, "32.0", "32.0"),
        (1e-5, "1.0E-5", "1.0e-5"),
        (np.nan, "NaN", "NaN"),
        (7, "7", "7"),
    ],
)
def test_java_number(value, java, das):
    assert java_number(value) == java
    assert java_number(value, das=True) == das


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("text", "String"),
        (1.5, "double"),
        (1, "int"),
        (np.float32(1), "float"),
        (np.int16(1), "short"),
        (np.array([1, 2], dtype="int8"), "byte"),
    ],
)
def test_attr_type(value, kind):
    assert attr_type(value) == kind


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (2629635.6, "30 days 10h 27m 16s"),  # CRW_sst_v1_0_monthly
        (86764.0, "1 day 0h 6m 4s"),  # erdMH1chla1day
        (690030.0, "7 days 23h 40m 30s"),  # erdMH1chla8day
    ],
)
def test_duration(seconds, text):
    assert _duration(seconds) == text


def test_float32_axes_are_rounded_to_seven_digits():
    """erdMH1chla8day: 89.979164 is used as 89.97916."""
    values = np.array([89.979164, -89.97917], dtype="float32")
    assert list(nice_doubles(values)) == [89.97916, -89.97917]


def test_spacing_of_a_descending_float32_axis():
    """CRW_sst_v3_1_monthly's latitude, as its real info table gives it."""
    lat = (89.975 - 0.05 * np.arange(3600)).astype("float32")
    assert _spacing(lat) == (
        ", evenlySpaced=true, averageSpacing=-0.049999999999999996"
    )


def test_spacing_of_uneven_times():
    # "0h 0m 0s" is inferred from "1 day 0h 6m 4s"; no real server checked
    times = pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]).values
    assert _spacing(times) == (", evenlySpaced=false, averageSpacing=30 days 0h 0m 0s")
