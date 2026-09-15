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

import numpy as np
import pandas as pd

__all__ = ["DimSelection", "ParsedQuery", "parse_griddap_query", "split_selectors"]

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


def _nearest_index(values: np.ndarray, target) -> int:
    """Index of the axis element nearest ``target``."""
    arr = np.asarray(values)
    if _axis_is_time(arr):
        as_int = arr.astype("datetime64[ns]").astype("int64")
        diffs = np.abs(as_int - np.datetime64(target, "ns").astype("int64"))
    else:
        diffs = np.abs(arr.astype("float64") - float(target))
    return int(np.argmin(diffs))


_LAST_RE = re.compile(r"^last\s*(?:-\s*(\d+(?:\.\d+)?))?$")


def _resolve_token(token: str, values: np.ndarray, *, default: int) -> int:
    """Resolve one endpoint token to an integer index."""
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
            return _nearest_index(values, target)
        idx = n - 1 - int(float(offset))
        if not 0 <= idx < n:
            msg = f"index {idx} out of range for axis of length {n}"
            raise ConstraintError(msg)
        return idx

    if paren:
        return _nearest_index(values, _to_comparable(inner, values))

    try:
        idx = int(inner)
    except ValueError as exc:
        msg = (
            f"cannot interpret {token!r} as an index; "
            "use (value) for coordinate values"
        )
        raise ConstraintError(msg) from exc
    if idx < 0:
        idx += n
    if not 0 <= idx < n:
        msg = f"index {idx} out of range for axis of length {n}"
        raise ConstraintError(msg)
    return idx


def parse_selector(selector: str, values: np.ndarray) -> DimSelection:
    """Parse one ``[...]`` selector against an axis's values."""
    n = len(values)
    parts = [p.strip() for p in _split_top_level(selector, ":")]
    if selector.strip() == "":
        return DimSelection(0, n - 1, 1)
    if len(parts) == 1:
        idx = _resolve_token(parts[0], values, default=0)
        return DimSelection(idx, idx, 1)
    if len(parts) == _RANGE_PARTS:
        start = _resolve_token(parts[0], values, default=0)
        stop = _resolve_token(parts[1], values, default=n - 1)
        stride = 1
    elif len(parts) == _STRIDED_PARTS:
        start = _resolve_token(parts[0], values, default=0)
        stride_text = parts[1].strip() or "1"
        try:
            stride = int(stride_text)
        except ValueError as exc:
            msg = f"stride must be an integer, got {stride_text!r}"
            raise ConstraintError(msg) from exc
        stop = _resolve_token(parts[2], values, default=n - 1)
    else:
        msg = f"too many ':' separated parts in selector [{selector}]"
        raise ConstraintError(msg)

    if stride < 1:
        msg = f"stride must be >= 1, got {stride}"
        raise ConstraintError(msg)
    if start > stop:
        # ERDDAP tolerates reversed coordinate ranges on descending axes
        start, stop = stop, start
    return DimSelection(start, stop, stride)


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

    for raw_token in _split_top_level(query, ","):
        token = raw_token.strip()
        if not token:
            continue
        name, selectors = split_selectors(token)
        if name in axes and not selectors:
            # a bare axis request, e.g. "?time" (erddapy's .csvp probe)
            variables.append(name)
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
            dim: parse_selector(sel, axes[dim])
            for dim, sel in zip(dim_order, selectors, strict=True)
        }
        if selections is None:
            selections = parsed
        elif parsed != selections:
            msg = "all variables in one griddap request must share the same subset"
            raise ConstraintError(msg)

    return ParsedQuery(variables, selections or full)
