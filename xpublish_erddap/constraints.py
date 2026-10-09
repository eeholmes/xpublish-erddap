"""Parse ERDDAP griddap constraint expressions into integer index selections.

ERDDAP's griddap query grammar, as used by erddapy and rerddap::

    var1[(2020-01-01):1:(2020-02-01)][(30):1:(40)],var2[...]
    var1[0:1:10][0:2:100]
    var1[last][0:1:last-3]
    var1[]

Values in parentheses are *coordinate values* (nearest match); bare values are
*integer indices*. ``last``/``last-N``/``last+N`` work in both forms. Values
are read with ERDDAP's own lenient parsers (``javaparse``). This module resolves
everything down to integer ``(start, stop, stride)`` triples with an inclusive
``stop``, which is how ERDDAP defines them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from xpublish_erddap import javaparse
from xpublish_erddap.catalog import nice_doubles
from xpublish_erddap.formats import java_number

__all__ = [
    "ConstraintError",
    "DimSelection",
    "NoMatchError",
    "ParsedQuery",
    "jsonp_name",
    "parse_griddap_query",
    "split_amp",
    "split_selectors",
]

#: ``[start:stride:stop]`` has three parts (``[start:stop]`` two).
_STRIDED_PARTS = 3


@dataclass(frozen=True)
class DimSelection:
    """An inclusive integer selection along one dimension."""

    start: int
    stop: int
    stride: int

    def as_slice(self) -> slice:
        """Return a numpy/xarray slice (exclusive stop)."""
        return slice(self.start, self.stop + 1, self.stride)

    @property
    def size(self) -> int:
        """Number of elements selected."""
        return len(range(self.start, self.stop + 1, self.stride))


@dataclass
class ParsedQuery:
    """Result of parsing a griddap query string."""

    variables: list[str]
    selections: dict[str, DimSelection]


class ConstraintError(ValueError):
    """Raised when a constraint expression cannot be parsed or resolved."""


class NoMatchError(ConstraintError):
    """A coordinate value is outside its axis: ERDDAP answers 404 (#57).

    Its text is ERDDAP's, minus the ``Not Found:`` the error body adds.
    """


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split on ``sep`` only outside parentheses.

    Needed because ISO 8601 values contain ``:`` — ``(2020-01-01T00:00:00Z)``
    must not be split on its colons.
    """
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def split_selectors(token: str) -> tuple[str, list[str]]:
    """Split ``name[a][b]`` into ``("name", ["a", "b"])``."""
    m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$", token, re.S)
    if not m:
        msg = f"cannot parse variable token {token!r}"
        raise ConstraintError(msg)
    name, rest = m.group(1), m.group(2).strip()
    selectors, depth, cur = [], 0, []
    for ch in rest:
        if ch == "[":
            depth += 1
            if depth == 1:
                cur = []
                continue
        elif ch == "]":
            depth -= 1
            if depth == 0:
                selectors.append("".join(cur))
                continue
        if depth >= 1:
            cur.append(ch)
    if depth != 0:
        msg = f"unbalanced brackets in {token!r}"
        raise ConstraintError(msg)
    return name, selectors


def _axis_is_time(values: np.ndarray) -> bool:
    return np.issubdtype(np.asarray(values).dtype, np.datetime64)


def _destination_double(text: str, values: np.ndarray) -> float:
    """A ``(value)`` as ERDDAP's destination double; NaN if it cannot be read.

    ``EDVTimeStampGridAxis.destinationToDouble``: on a time axis, text shaped
    like a date (``Calendar2.isIsoDate``) is read leniently as one, in epoch
    seconds; anything else, on any axis, is ``String2.parseDouble``. Kept a
    float, never ``datetime64[ns]``, which wraps silently past 2262.
    """
    if _axis_is_time(values) and javaparse.is_iso_date(text):
        try:
            return javaparse.iso_to_epoch_seconds(text)
        except ValueError:
            return float("nan")
    return javaparse.parse_double(text)


def _last_value(values: np.ndarray) -> float:
    """``EDVGridAxis.lastDestinationValue``: the last value as a double."""
    arr = np.asarray(values)
    if _axis_is_time(arr):
        return float(_axis_seconds(arr[-1:])[0])
    return float(nice_doubles(arr[-1:])[0])


def _convert_last(token: str, values: np.ndarray, role: str) -> str:
    """``EDDGrid.convertLast``: ``last[±n]`` to an index, ``(last[±x])`` to a ``(value)``.

    ``+`` or ``-`` (with spaces around it, if wanted); ``x`` is any number in
    value units (seconds for time), ``n`` a strict integer. The result goes
    through the same checks as an index or value the user wrote.
    """
    paren = token.startswith("(")
    text = token[1:-1].strip() if paren else token
    text = text[len("last") :].strip()
    if not text:
        return f"({java_number(_last_value(values))})" if paren else str(len(values) - 1)
    if text[0] not in "+-":
        msg = f'Query error: Unexpected character after "last" in {role}={token}.'
        raise ConstraintError(msg)
    sign = -1 if text[0] == "-" else 1
    text = text[1:].strip()
    if paren:
        offset = javaparse.parse_double(text)
        if np.isnan(offset):
            msg = f"Query error: The +/- value in {role}={token} isn't valid."
            raise ConstraintError(msg)
        return f"({java_number(_last_value(values) + sign * offset)})"
    offset = javaparse.strict_int(text)
    if offset is None:
        msg = (
            f"Query error: The +/- index value in {role}={token} isn't an integer.\n"
            f'(Cause: java.lang.NumberFormatException: For input string: "{text}")'
        )
        raise ConstraintError(msg)
    return str(len(values) - 1 + sign * offset)


#: ``MustBe.THERE_IS_NO_DATA`` followed by ``EDStatic.messages.queryError``.
_NO_MATCH = "Your query produced no matching results. Query error: "

#: ``Math2.fEps``, a float, and ``Math2.dEps``.
_F_EPS = float(np.float32(1e-5))
_D_EPS = 1e-13
_DIGITS_FOR_DOUBLE_AXES = 9


def _almost_equal(digits: int, d1: float, d2: float) -> bool:
    """``Math2.almostEqual(nSignificantDigits, d1, d2)``."""
    eps = _D_EPS if digits >= 6 else _F_EPS  # noqa: PLR2004
    ten = 10.0**digits
    with np.errstate(all="ignore"):
        if abs(d2) < eps:
            return abs(d1) < eps or bool(np.rint(d2 / d1 * ten) == ten)
        return bool(np.rint(d1 / d2 * ten) == ten)


def _iso_seconds(seconds: float) -> str:
    """``Calendar2.epochSecondsToIsoStringTZ``: rounded to the millisecond."""
    millis = int(np.rint(seconds * 1000))
    try:
        when = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=millis)
    except OverflowError:
        return java_number(seconds)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _axis_seconds(values: np.ndarray) -> np.ndarray:
    """A time axis as epoch seconds (ERDDAP's destination values)."""
    return values.astype("datetime64[us]").astype("int64") / 1e6


def check_in_range(
    values: np.ndarray,
    value: float,
    text: str,
    *,
    role: str,
    where: str = "",
) -> None:
    """Refuse a coordinate ``value`` outside the axis, as ERDDAP does (#57).

    Ported from ``EDDGrid.parseAxisBrackets`` (``validateGreaterThanThrowOrRepair``,
    then ``validateLessThanThrowOrRepair``) and
    ``EDVGridAxis.initializeAverageSpacingAndCoarseMinMax``
    (github.com/ERDDAP/erddap ``main``, 2026-10-08). The allowed range is the
    axis's min and max widened by half its average spacing (for a one-value
    axis, by ``max(|min| / 100, 0.01)``), compared to 13 significant digits
    for time, 9 for a double axis and 5 for any other. A value inside it but
    off the axis still snaps to the nearest element, as before.

    ``text`` is the value as the user wrote it, for the message; ``role`` is
    ``"Start"`` or ``"Stop"``; ``where`` is ``For variable=... axis#N=...``.
    """
    arr = np.asarray(values)
    is_time = _axis_is_time(arr)
    if is_time:
        digits, numeric = 13, _axis_seconds(arr)
    else:
        digits = _DIGITS_FOR_DOUBLE_AXES if arr.dtype == np.float64 else 5
        # float32 values become 7-digit doubles, so the margin (and its text)
        # is ERDDAP's: erdMH1chla8day says -90.00000333294744, raw floats give
        # -90.00000508655744.
        numeric = nice_doubles(arr)
    low, high = float(np.min(numeric)), float(np.max(numeric))
    if len(numeric) >= 2:  # noqa: PLR2004
        rough = abs((numeric[-1] - numeric[0]) / (len(numeric) - 1)) / 2
    else:
        rough = max(abs(low) / 100, 0.01)
    coarse_low, coarse_high = low - rough, high + rough

    def show(x: float, element: int | None = None) -> str:
        if is_time:
            return _iso_seconds(x)
        # An axis element prints at the axis's own precision (float32: 89.75625).
        return java_number(arr[element] if element is not None else x)

    first = f"{where}: " if where else ""
    if not (value >= coarse_low or _almost_equal(digits, value, coarse_low)):
        msg = (
            f'{role}="{text}" is less than the axis minimum={show(low, int(np.argmin(numeric)))}'
            f" (and even {show(coarse_low)})."
        )
        raise NoMatchError(_NO_MATCH + first + msg)
    if not (value <= coarse_high or _almost_equal(digits, value, coarse_high)):
        # ERDDAP passes the message template as its own first argument, so
        # the template shows through before the sentence. Copied as it is, so
        # the error body matches a real server's.
        template = '{0}="{1}" is greater than the axis maximum={2} (and even {3}).'
        msg = (
            f'{template}="{role}" is greater than the axis maximum={text}'
            f" (and even {show(high, int(np.argmax(numeric)))})."
        )
        raise NoMatchError(_NO_MATCH + first + msg)


def _nearest_index(values: np.ndarray, target: float) -> int:
    """Index of the axis element nearest ``target``, a destination double.

    On an exact tie ERDDAP picks the *larger* coordinate value, whichever way
    the axis runs (checked against real servers; see issue #11).
    """
    arr = np.asarray(values)
    numeric = _axis_seconds(arr) if _axis_is_time(arr) else arr.astype("float64")
    diffs = np.abs(numeric - target)
    tied = np.flatnonzero(diffs == diffs.min())
    return int(tied[np.argmax(numeric[tied])])


def _resolve_token(
    token: str,
    values: np.ndarray,
    *,
    role: str = "Start",
    where: str = "",
) -> int:
    """Resolve one start or stop to an index, as ``EDDGrid.parseAxisBrackets`` does.

    ``last`` forms are converted first (``_convert_last``). A ``(value)`` must
    be readable (else a 400) and inside the axis (else a 404, #57), then snaps
    to the nearest element. An index must be digits only, at most n - 1:
    ``-1`` is refused, not counted from the end. ``role`` and ``where`` word
    the errors as ERDDAP does.
    """
    token = token.strip()
    n = len(values)
    head = f"Query error: {where}: " if where else "Query error: "

    if token.startswith(("last", "(last")):
        token = _convert_last(token, values, role)

    if token.startswith("("):
        inner = token[1:-1].strip()
        if not inner:
            msg = f"{head}The {role} value inside () is missing."
            raise ConstraintError(msg)
        target = _destination_double(inner, values)
        if np.isnan(target):
            # A 400, before the range checks.
            msg = f"{head}{role}=NaN (invalid format?) isn't allowed."
            raise ConstraintError(msg)
        check_in_range(values, target, inner, role=role, where=where)
        return _nearest_index(values, target)

    if not re.fullmatch(r"[0-9]+", token) or int(token) > n - 1:
        msg = f'{head}{role}="{token}" is invalid.  It must be an integer between 0 and {n - 1}.'
        raise ConstraintError(msg)
    return int(token)


def parse_selector(
    selector: str,
    values: np.ndarray,
    *,
    allow_reversed: bool = True,
    where: str = "",
) -> DimSelection:
    """Parse one ``[...]`` selector against an axis's values.

    ``allow_reversed``: ERDDAP swaps a range given against the axis order for
    data-variable requests, but refuses it for axis-only requests. ``where``
    (``For variable=sst axis#1=latitude``) opens the error for a value off the
    axis (#57).
    """
    n = len(values)
    head = "Query error: "
    if where:
        where = f'{where} Constraint="[{selector}]"'
        head = f"Query error: {where}: "
    start_kw = {"role": "Start", "where": where}
    stop_kw = {"role": "Stop", "where": where}
    parts = [p.strip() for p in _split_top_level(selector, ":")]
    if selector.strip() == "":
        return DimSelection(0, n - 1, 1)
    if len(parts) == 1:
        idx = _resolve_token(parts[0], values, **start_kw)
        return DimSelection(idx, idx, 1)
    stride = 1
    if len(parts) >= _STRIDED_PARTS:
        # ERDDAP reads the stride first (String2.parseInt, which rounds), and
        # whatever follows the second colon is the stop, colons and all
        stride_text = parts[1]
        stride = javaparse.parse_int(stride_text)
        if stride < 1 or stride == javaparse.INT_MAX:
            msg = f"{head}Stride={stride_text} is invalid."
            raise ConstraintError(msg)
        parts = [parts[0], ":".join(parts[2:])]
    start = _resolve_token(parts[0], values, **start_kw)
    stop = _resolve_token(parts[1], values, **stop_kw)

    if start > stop:
        if not allow_reversed:
            msg = f"start > stop in [{selector}]: give the range in axis order"
            raise ConstraintError(msg)
        start, stop = stop, start
    return DimSelection(start, stop, stride)


#: ``Message.ERROR_JSONP_FUNCTION_NAME``, which does not name the function.
_JSONP_NAME = (
    "Query error: That jsonp functionName isn't allowed. The first character must be an "
    'ISO 8859-1 letter or "_".  Each optional subsequent character must be an ISO 8859-1 '
    'letter, "_", a digit, or ".".'
)


def split_amp(query: str) -> list[str]:
    r"""``Table.getDapQueryParts``: a query's ``&``-separated parts.

    Splits an already percent-decoded query at each ``&`` outside double
    quotes (``\`` escapes the next character). At least one part: the first
    is the variables and constraints (``""`` if none), the rest are
    ``&``-clauses.
    """
    text = query + "&"  # the last one triggers the final part
    parts, start, in_quotes, po = [], 0, False, 0
    while po < len(text):
        ch = text[po]
        if ch == "\\":
            po += 1
        elif ch == '"':
            in_quotes = not in_quotes
        elif ch == "&" and not in_quotes:
            parts.append(text[start:po])
            start = po + 1
        po += 1
    if in_quotes:
        msg = "Query error: A closing doublequote is missing."
        raise ConstraintError(msg)
    return parts


def jsonp_name(parts: list[str]) -> str | None:
    """The function name of a ``.jsonp=`` clause, or None; refuses an unsafe name.

    ``EDStatic.getJsonpFromQuery`` and ``Erddap.doGet``: the first part that
    starts with ``.jsonp=``, checked with ``String2.isJsonpNameSafe``.
    """
    for part in parts:
        if part.startswith(".jsonp="):
            name = part[len(".jsonp=") :]
            if not javaparse.is_jsonp_name_safe(name):
                raise ConstraintError(_JSONP_NAME)
            return name
    return None


def _parse_axis_request(
    name: str,
    selectors: list[str],
    axes: dict[str, np.ndarray],
    dim_order: list[str],
) -> DimSelection:
    """Selection for an axis-only request such as ``?time[(last)]``.

    Plain ``?time`` (erddapy's ``.csvp`` probe) has no selector and never
    gets here.
    """
    if len(selectors) > 1:
        msg = f"axis {name} takes one selector, got {len(selectors)}"
        raise ConstraintError(msg)
    where = f"For variable={name} axis#{dim_order.index(name)}={name}"
    return parse_selector(selectors[0], axes[name], allow_reversed=False, where=where)


def parse_griddap_query(
    query: str,
    axes: dict[str, np.ndarray],
    dim_order: list[str],
    known_variables: list[str],
) -> ParsedQuery:
    """Parse a full griddap query string.

    Args:
        query: the raw (already percent-decoded) query string.
        axes: mapping of axis name -> its values.
        dim_order: the dataset's axis names, in order.
        known_variables: data variable names available in the dataset.

    Returns:
        The requested variables and the resolved per-dimension selections.
    """
    full = {d: DimSelection(0, len(axes[d]) - 1, 1) for d in dim_order}
    query = (query or "").strip()
    if not query:
        return ParsedQuery(list(known_variables), full)

    variables: list[str] = []
    selections: dict[str, DimSelection] | None = None
    axis_selections: dict[str, DimSelection] = {}

    for raw_token in _split_top_level(query, ","):
        token = raw_token.strip()
        if not token:
            continue
        name, selectors = split_selectors(token)
        if name in axes:
            variables.append(name)
            if selectors:
                axis_selections[name] = _parse_axis_request(name, selectors, axes, dim_order)
            continue
        if name not in known_variables:
            msg = f"unknown variable {name!r}"
            raise ConstraintError(msg)
        variables.append(name)
        if not selectors:
            continue
        if len(selectors) != len(dim_order):
            msg = (
                f"{name} expects {len(dim_order)} selectors "
                f"({', '.join(dim_order)}), got {len(selectors)}"
            )
            raise ConstraintError(msg)
        parsed = {
            dim: parse_selector(
                sel,
                axes[dim],
                where=f"For variable={name} axis#{i}={dim}",
            )
            for i, (dim, sel) in enumerate(zip(dim_order, selectors, strict=True))
        }
        if selections is None:
            selections = parsed
        elif parsed != selections:
            msg = "all variables in one griddap request must share the same subset"
            raise ConstraintError(msg)

    out = dict(selections or full)
    for dim, sel in axis_selections.items():
        if selections is not None and selections[dim] != sel:
            msg = "all variables in one griddap request must share the same subset"
            raise ConstraintError(msg)
        out[dim] = sel
    return ParsedQuery(variables, out)
