"""ERDDAP's own number and date parsing, ported so constraints read as ERDDAP reads them (#58).

ERDDAP does not use strict parsers: ``Calendar2.parseISODateTime`` rolls
``2019-01-32`` over to ``2019-02-01`` ("It's not a bug, it's a feature", its
documentation says) and reads a space as ``+`` (a raw ``+`` in a URL arrives
as a space), and ``String2.parseDouble`` returns NaN instead of raising. Python's
parsers differ on each point, so the methods are ported here, from
github.com/ERDDAP/erddap ``main`` (2026-10-08):

- ``com.cohort.util.String2.parseDouble``, ``String2.parseInt``,
  ``String2.isJsonpNameSafe``
- ``com.cohort.util.Calendar2.parseISODateTime``, ``parseN``,
  ``isoStringToMillis``, ``isIsoDate``

Each returns NaN (or raises ``ValueError``) where ERDDAP returns NaN or throws.
"""

from __future__ import annotations

import math
import re

__all__ = [
    "is_iso_date",
    "is_jsonp_name_safe",
    "iso_to_epoch_seconds",
    "parse_double",
    "parse_int",
]

#: ``Integer.MAX_VALUE``, which ``String2.parseInt`` returns for "trouble".
INT_MAX = 2**31 - 1
_LONG_MAX = 2**63 - 1

#: What Java's ``Double.parseDouble`` reads, less the forms ``parseDouble``
#: rejects anyway (``Infinity``, ``NaN``, hex floats). No ``_`` separators,
#: which Python's ``float`` allows.
_JAVA_DOUBLE = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[fFdD]?")
_JAVA_INT = re.compile(r"[+-]?[0-9]+")
_HEX = re.compile(r"0[xX][0-9a-fA-F]+")

#: ``Calendar2.ISO_DATE_PATTERN``: whether a time axis reads text as a date.
_ISO_DATE = re.compile(r"-?[0-9]{4}-[01]?[0-9](|-[0-9].*)", re.S)

#: ``parseISODateTime``'s separators: ``-`` ``-`` (any) ``:`` ``:`` ``.`` ``±``
#: ``:`` (any), between year month day hour minute second millis tzHour tzMinute.
_ANY = "\0"
_SEPARATORS = ("-", "-", _ANY, ":", ":", ".", "±", ":", _ANY)


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def parse_double(text: str) -> float:
    """``String2.parseDouble``: a finite double, or NaN.

    Hex integers (``0x1F``) are read; ``NaN``, ``Infinity``, ``1e400`` and
    anything Java would not parse are NaN.
    """
    s = (text or "").strip()
    if not s or not (_is_digit(s[0]) or s[0] in "+-."):
        return math.nan
    if s.startswith(("0x", "0X")):
        if not _HEX.fullmatch(s):
            return math.nan
        value = int(s[2:], 16)
        return float(value) if value <= _LONG_MAX else math.nan
    if not _JAVA_DOUBLE.fullmatch(s):
        return math.nan
    value = float(s.rstrip("fFdD"))
    return value if math.isfinite(value) else math.nan


def parse_int(text: str) -> int:
    """``String2.parseInt``: an int, or ``INT_MAX`` for trouble.

    Lenient: hex is read, and a decimal rounds (``1.5`` -> 2), as in Java.
    """
    s = (text or "").strip()
    if not s or not (_is_digit(s[0]) or s[0] in "+-."):
        return INT_MAX
    if s.startswith(("0x", "0X")):
        if not _HEX.fullmatch(s):
            return INT_MAX
        # Java casts the long to int: the lowest 32 bits, signed.
        low = int(s[2:], 16) & 0xFFFFFFFF
        return low - 2**32 if low >= 2**31 else low
    if _JAVA_INT.fullmatch(s):
        value = int(s)
        if -(2**31) <= value <= INT_MAX:
            return value
    value = parse_double(s)
    if math.isnan(value):
        return INT_MAX
    # Math2.roundToInt: rounds half up; out of range is trouble.
    rounded = math.floor(value + 0.5)
    return rounded if -(2**31) <= rounded < INT_MAX else INT_MAX


def _is_letter(ch: str) -> bool:
    """``String2.isLetter``: A-Z, a-z and the ISO 8859-1 letters."""
    return (
        "A" <= ch <= "Z"
        or "a" <= ch <= "z"
        or ("\u00c0" <= ch <= "\u00ff" and ch not in "\u00d7\u00f7")
    )


def is_jsonp_name_safe(name: str) -> bool:
    """``String2.isJsonpNameSafe``: dotted words of letters, ``_`` and digits.

    Each word starts with a letter or ``_``; there is at least one, none is
    empty (so no leading, trailing or doubled ``.``), and the name is at most
    255 characters.
    """
    if not name or len(name) > 255 or name.endswith("."):  # noqa: PLR2004
        return False
    for word in name.split("."):
        if not word or not (_is_letter(word[0]) or word[0] == "_"):
            return False
        if not all(_is_letter(c) or "0" <= c <= "9" or c == "_" for c in word[1:]):
            return False
    return True


def strict_int(text: str) -> int | None:
    """Java's ``Integer.parseInt``: an optional sign and digits, in int range."""
    if not _JAVA_INT.fullmatch(text):
        return None
    value = int(text)
    return value if -(2**31) <= value <= INT_MAX else None


def is_iso_date(text: str) -> bool:
    """``Calendar2.isIsoDate``: whether a time axis reads ``text`` as a date."""
    return bool(_ISO_DATE.fullmatch((text or "").strip()))


class _Trouble(ValueError):
    pass


def _java_div(a: int, b: int) -> int:
    """Java's ``int / int``: truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _parse_n(s: str, results: list[int]) -> None:  # noqa: C901, PLR0912, PLR0915
    """``Calendar2.parseN``: read numbers between ``_SEPARATORS`` into ``results``.

    Stops quietly at the first part with no digits (so ``2019-01-01Tjunk`` is
    midnight); raises ``_Trouble`` where ERDDAP sets ``resultsN[0]`` to
    ``Integer.MAX_VALUE``.
    """
    s = s.strip()
    n = len(s)
    if n < 1 or not (s[0] == "-" or _is_digit(s[0])):
        raise _Trouble
    po2 = -1
    pm_factor = 1
    m_mode = s[0] == "-"  # a leading '-' belongs to the number
    n_parts = len(_SEPARATORS)
    part = 0
    while part < n_parts:
        if po2 + 1 >= n:
            part += 1
            continue
        po1 = po2 = po2 + 1
        if m_mode:
            if po2 < n and s[po2] == "-":
                po2 += 1
            else:
                raise _Trouble
        while po2 < n and _is_digit(s[po2]):
            po2 += 1
        if po2 == po1:
            return  # no number: done
        digits = s[po1:po2]
        before = _SEPARATORS[part - 1] if part > 0 else ""
        if before == ".":
            # fractional seconds, truncated to millis
            results[part] = math.trunc(1000 * parse_double("0." + digits))
        elif (
            before == "±"
            and _SEPARATORS[part] == ":"
            and po2 - po1 >= (1 if s[po1] == "-" else 0) + 3
        ):
            # a zone written -0830 or 830: hours and minutes
            ti = parse_int(digits)
            results[part] = _java_div(ti, 100)
            results[part + 1] = ti - 100 * _java_div(ti, 100)
            part += 1
        elif part > 1 and _SEPARATORS[part - 2] == "±" and before == ":":
            # the zone's minutes take the sign of its hours
            results[part] = parse_int(digits)
            if results[part] != INT_MAX:
                results[part] *= pm_factor
        else:
            results[part] = parse_int(digits)
            if before == "±":
                pm_factor = -1 if s[po1] == "-" else 1
        if results[part] == INT_MAX:
            raise _Trouble
        if po2 >= n:
            return
        m_mode = False
        ch = "." if s[po2] == "," else s[po2]
        separator = _SEPARATORS[part]
        if separator == _ANY:
            pass
        elif separator == "±":
            if ch == "-":
                po2 -= 1  # the number starts with '-'
                m_mode = True
            elif ch != "+":
                raise _Trouble
        elif ch != separator:
            # a missing ':' or '.': skip ahead to the time zone, if there is one
            if separator in ":." and part < n_parts - 1 and "±" in _SEPARATORS[part + 1 :]:
                part = _SEPARATORS.index("±", part + 1)
                if ch == "-":
                    po2 -= 1
                    m_mode = True
                elif ch != "+":
                    raise _Trouble
            else:
                raise _Trouble
        part += 1


def _days_from_civil(year: int, month: int, day: int) -> int:
    """Days since 1970-01-01 in the proleptic Gregorian calendar, any year."""
    year -= month <= 2  # noqa: PLR2004
    era = year // 400
    yoe = year - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1  # noqa: PLR2004
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def iso_to_epoch_seconds(text: str) -> float:
    """``Calendar2.isoStringToEpochSeconds``: lenient ISO 8601 to epoch seconds.

    Missing trailing parts default to ``1970-01-01T00:00:00``; out-of-range
    fields roll over (``2019-02-30T25:61`` is ``2019-03-03T02:01``); a space
    is a ``+``; ``Z``, ``UTC`` or no zone is UTC; millis are kept. Raises
    ``ValueError`` where ERDDAP throws.
    """
    s = (text or "").strip()
    negative = s.startswith("-")
    if negative:
        s = s[1:]
    if not s or not _is_digit(s[0]):
        msg = f"dateTime={text!r} does not start with a digit"
        raise ValueError(msg)
    # year month day hour minute second millis tzHour tzMinute
    ymd = [INT_MAX, 1, 1, 0, 0, 0, 0, 0, 0]
    s = s.strip()
    if s[-1].lower() == "z":
        s = s[:-1].strip()
    if len(s) >= 3 and s[-3:].lower() in ("utc", "gmt"):  # noqa: PLR2004
        s = s[:-3].strip()
    # A raw '+' in a URL is decoded as a space: read it as '+' again.
    s = s.replace(" ", "+")
    try:
        _parse_n(s, ymd)
    except _Trouble:
        ymd[0] = INT_MAX
    if ymd[0] == INT_MAX:
        msg = f"dateTime={text!r} has an invalid format"
        raise ValueError(msg)
    ymd[3] -= ymd[7]
    ymd[4] -= ymd[8]
    year = -ymd[0] if negative else ymd[0]
    # ZonedDateTime.of(year, 1, 1).plusMonths(...).plusDays(...)...: each
    # field is added to the one before, so overflow rolls over.
    months = year * 12 + ymd[1] - 1
    days = _days_from_civil(months // 12, months % 12 + 1, 1) + ymd[2] - 1
    millis = (((days * 24 + ymd[3]) * 60 + ymd[4]) * 60 + ymd[5]) * 1000 + ymd[6]
    return millis / 1000
