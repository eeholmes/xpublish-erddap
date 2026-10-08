"""Parse ERDDAP griddap constraint expressions into integer index selections.

ERDDAP's griddap query grammar, as used by erddapy and rerddap::

    var1[(2020-01-01):1:(2020-02-01)][(30):1:(40)],var2[...]
    var1[0:1:10][0:2:100]
    var1[last][0:1:last-3]
    var1[]

Values in parentheses are *coordinate values* (nearest match); bare values are
*integer indices*. ``last``/``last-N`` work in both forms. This module resolves
everything down to integer ``(start, stop, stride)`` triples with an inclusive
``stop``, which is how ERDDAP defines them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from xpublish_erddap.formats import java_number

__all__ = [
    "ConstraintError",
    "DimSelection",
    "NoMatchError",
    "ParsedQuery",
    "parse_griddap_query",
    "split_selectors",
]

#: ``[start:stop]`` has two parts; ``[start:stride:stop]`` has three.
_RANGE_PARTS = 2
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


def _to_comparable(value: str, values: np.ndarray):
    """Coerce a coordinate-value token to something comparable with the axis."""
    if _axis_is_time(values):
        text = value.strip()
        # ERDDAP also accepts epoch seconds for time
        try:
            return np.datetime64(pd.Timestamp(float(text), unit="s").tz_localize(None))
        except (TypeError, ValueError):
            pass
        ts = pd.Timestamp(text)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return np.datetime64(ts)
    return float(value)


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
    return values.astype("datetime64[ns]").astype("int64") / 1e9


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
        numeric = arr.astype("float64")
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


def _seconds_of(target, values: np.ndarray) -> float:
    """``target`` (from ``_to_comparable``) as the axis's destination double."""
    if _axis_is_time(values):
        return float(np.datetime64(target, "ns").astype("int64")) / 1e9
    return float(target)


def _nearest_index(values: np.ndarray, target) -> int:
    """Index of the axis element nearest ``target``.

    On an exact tie ERDDAP picks the *larger* coordinate value, whichever way
    the axis runs (checked against real servers; see issue #11).
    """
    arr = np.asarray(values)
    if _axis_is_time(arr):
        numeric = arr.astype("datetime64[ns]").astype("int64")
        diffs = np.abs(numeric - np.datetime64(target, "ns").astype("int64"))
    else:
        numeric = arr.astype("float64")
        diffs = np.abs(numeric - float(target))
    tied = np.flatnonzero(diffs == diffs.min())
    return int(tied[np.argmax(numeric[tied])])


_LAST_RE = re.compile(r"^last\s*(?:-\s*(\d+(?:\.\d+)?))?$")


def _resolve_token(
    token: str,
    values: np.ndarray,
    *,
    default: int,
    role: str = "Start",
    where: str = "",
) -> int:
    """Resolve one endpoint token to an integer index.

    A ``(value)`` outside the axis raises ``NoMatchError`` (#57); ``role``
    and ``where`` only word that error.
    """
    token = token.strip()
    n = len(values)
    if token == "":
        return default

    paren = token.startswith("(") and token.endswith(")")
    inner = token[1:-1].strip() if paren else token

    m = _LAST_RE.match(inner)
    if m:
        offset = m.group(1)
        if offset is None:
            return n - 1
        if paren:
            # (last-d): d is in *value* space, per ERDDAP docs
            arr = np.asarray(values)
            if _axis_is_time(arr):
                target = arr[-1] - np.timedelta64(int(float(offset)), "s")
            else:
                target = arr.astype("float64")[-1] - float(offset)
            seconds = _seconds_of(target, arr)
            # ERDDAP's convertLast turns it into the value's text, in Java's form.
            check_in_range(arr, seconds, java_number(seconds), role=role, where=where)
            return _nearest_index(values, target)
        idx = n - 1 - int(float(offset))
        if not 0 <= idx < n:
            msg = f"index {idx} out of range for axis of length {n}"
            raise ConstraintError(msg)
        return idx

    if paren:
        target = _to_comparable(inner, values)
        check_in_range(values, _seconds_of(target, values), inner, role=role, where=where)
        return _nearest_index(values, target)

    try:
        idx = int(inner)
    except ValueError as exc:
        msg = f"cannot interpret {token!r} as an index; use (value) for coordinate values"
        raise ConstraintError(msg) from exc
    if idx < 0:
        idx += n
    if not 0 <= idx < n:
        msg = f"index {idx} out of range for axis of length {n}"
        raise ConstraintError(msg)
    return idx


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
    if where:
        where = f'{where} Constraint="[{selector}]"'
    start_kw = {"role": "Start", "where": where}
    stop_kw = {"role": "Stop", "where": where}
    parts = [p.strip() for p in _split_top_level(selector, ":")]
    if selector.strip() == "":
        return DimSelection(0, n - 1, 1)
    if len(parts) == 1:
        idx = _resolve_token(parts[0], values, default=0, **start_kw)
        return DimSelection(idx, idx, 1)
    if len(parts) == _RANGE_PARTS:
        start = _resolve_token(parts[0], values, default=0, **start_kw)
        stop = _resolve_token(parts[1], values, default=n - 1, **stop_kw)
        stride = 1
    elif len(parts) == _STRIDED_PARTS:
        start = _resolve_token(parts[0], values, default=0, **start_kw)
        stride_text = parts[1].strip() or "1"
        try:
            stride = int(stride_text)
        except ValueError as exc:
            msg = f"stride must be an integer, got {stride_text!r}"
            raise ConstraintError(msg) from exc
        stop = _resolve_token(parts[2], values, default=n - 1, **stop_kw)
    else:
        msg = f"too many ':' separated parts in selector [{selector}]"
        raise ConstraintError(msg)

    if stride < 1:
        msg = f"stride must be >= 1, got {stride}"
        raise ConstraintError(msg)
    if start > stop:
        if not allow_reversed:
            msg = f"start > stop in [{selector}]: give the range in axis order"
            raise ConstraintError(msg)
        start, stop = stop, start
    return DimSelection(start, stop, stride)


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
