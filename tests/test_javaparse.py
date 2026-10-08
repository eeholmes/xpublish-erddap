"""ERDDAP's lenient number and date parsing, ported (#58).

Expected values follow ERDDAP's Calendar2 and String2; the ones that matter
to users are also parity cases against coastwatch's jplMURSST41.
"""

import math
from datetime import UTC, datetime

import pytest

from xpublish_erddap.javaparse import (
    INT_MAX,
    is_iso_date,
    iso_to_epoch_seconds,
    parse_double,
    parse_int,
    strict_int,
)


def utc(*args) -> float:
    return datetime(*args, tzinfo=UTC).timestamp()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2019-01-01", utc(2019, 1, 1)),
        ("2019-01-01T12:30:15Z", utc(2019, 1, 1, 12, 30, 15)),
        ("2019", utc(2019, 1, 1)),
        ("2019-01", utc(2019, 1, 1)),
        ("2019-1-2 12:00", utc(2019, 1, 2, 12)),
        ("2019-01-01 12:00 UTC", utc(2019, 1, 1, 12)),
        ("2019-01-01T12:00:00.5Z", utc(2019, 1, 1, 12) + 0.5),
        ("2019-01-01T12:00:00,25", utc(2019, 1, 1, 12) + 0.25),
        ("2019-01-01T12:00:00.123456789", utc(2019, 1, 1, 12) + 0.123),
        # "It is lenient; so Jan 32 is converted to Feb 1"
        ("2019-01-32", utc(2019, 2, 1)),
        ("2019-03-00", utc(2019, 2, 28)),
        ("2019-13-01", utc(2020, 1, 1)),
        ("2019-00-01", utc(2018, 12, 1)),
        ("2019-02-30T25:61:00Z", utc(2019, 3, 3, 2, 1)),
        # trailing junk ends the parse
        ("2019-01-01Tgarbage", utc(2019, 1, 1)),
        # zones: + or a space (a raw "+" in a URL), hh, hhmm, hh:mm
        ("2013-01-02T03:00:00+08:00", utc(2013, 1, 1, 19)),
        ("2013-01-02T03:00:00 08:00", utc(2013, 1, 1, 19)),
        ("2013-01-02T03:00:00+08", utc(2013, 1, 1, 19)),
        ("2013-01-02T03:00:00+0800", utc(2013, 1, 1, 19)),
        ("2013-01-02T03:00:00 0800", utc(2013, 1, 1, 19)),
        ("2013-01-01T22:00:00-08:00", utc(2013, 1, 2, 6)),
        ("2013-01-01T22:00:00-0830", utc(2013, 1, 2, 6, 30)),
        ("2013-01-01T22:00-08:00", utc(2013, 1, 2, 6)),
        # far dates do not overflow
        ("3000-01-01", utc(3000, 1, 1)),
        ("1500-06-01", utc(1500, 6, 1)),
    ],
)
def test_iso_to_epoch_seconds(text, expected):
    assert iso_to_epoch_seconds(text) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("text", ["", "abc", "T2019", "2019:01", "2019-01-01T12x00"])
def test_iso_to_epoch_seconds_refuses(text):
    with pytest.raises(ValueError, match="dateTime"):
        iso_to_epoch_seconds(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2019-01-01", True),
        ("2019-1", True),
        ("2019-01-01T00:00:00Z", True),
        ("-0001-01", True),
        ("2019", False),  # a number: read as epoch seconds
        ("20190102", False),
        ("1.5e9", False),
        ("notadate", False),
    ],
)
def test_is_iso_date(text, expected):
    assert is_iso_date(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.5", 1.5),
        (" 2 ", 2.0),
        ("+5", 5.0),
        (".5", 0.5),
        ("-1e3", -1000.0),
        ("1.5e9", 1.5e9),
        ("1.0d", 1.0),
        ("0x1F", 31.0),
    ],
)
def test_parse_double(text, expected):
    assert parse_double(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "abc", "NaN", "Infinity", "-Infinity", "1e400", "1_000", "1.2.3", "0x"],
)
def test_parse_double_nan(text):
    assert math.isnan(parse_double(text))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12", 12),
        ("-12", -12),
        ("+12", 12),
        ("1.5", 2),
        ("0x10", 16),
        ("x", INT_MAX),
        ("", INT_MAX),
        ("2147483648", INT_MAX),
    ],
)
def test_parse_int(text, expected):
    assert parse_int(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("5", 5), ("+5", 5), ("-5", -5), ("1.5", None), ("x", None), ("", None), ("1_0", None)],
)
def test_strict_int(text, expected):
    assert strict_int(text) == expected
