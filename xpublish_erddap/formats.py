"""Serialize a subset xarray Dataset into ERDDAP's response formats.

Only the formats erddapy and rerddap actually request are implemented:
``.dds``, ``.das``, ``.csvp``, ``.csv``, ``.csv0``, ``.json``, ``.nc``.
The HTML interfaces (``.html``, ``.graph``) are deliberately out of scope.

ERDDAP's exact spelling matters here. erddapy parses the DDS with
``data.split("GRID")``, so the uppercase ``GRID``/``ARRAY``/``MAPS`` keywords
are load-bearing even though DAP2 does not require them.
"""

from __future__ import annotations

import io
import itertools
import json

import numpy as np
import pandas as pd
import xarray as xr

from xpublish_erddap.catalog import coverage_globals, nice_doubles

__all__ = [
    "CONTENT_TYPES",
    "NCML_NS",
    "TIME_UNITS",
    "das_response",
    "dds_response",
    "format_value",
    "info_table",
    "ncml_response",
    "to_csv",
    "to_erddap_json",
    "to_netcdf_bytes",
]

TIME_UNITS = "seconds since 1970-01-01T00:00:00Z"

#: NcML namespace. erddapy >=3.2 parses the ``.ncml`` response with this exact
#: URI -- note the ``https`` scheme, which older NcML documents spell ``http``.
NCML_NS = "https://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2"

CONTENT_TYPES = {
    "das": "text/plain",
    "dds": "text/plain",
    "csv": "text/csv",
    "csv0": "text/csv",
    "csvp": "text/csv",
    "tsv": "text/tab-separated-values",
    "json": "application/json",
    "nc": "application/x-netcdf",
    "ncml": "application/xml",
    "htmlTable": "text/html",
}

_DAP_TYPES = {
    np.dtype("int8"): "Byte",
    np.dtype("uint8"): "Byte",
    np.dtype("int16"): "Int16",
    np.dtype("uint16"): "UInt16",
    np.dtype("int32"): "Int32",
    np.dtype("uint32"): "UInt32",
    np.dtype("int64"): "Float64",  # DAP2 has no 64-bit int
    np.dtype("uint64"): "Float64",
    np.dtype("float32"): "Float32",
    np.dtype("float64"): "Float64",
}


def _dtype_of(obj) -> np.dtype:
    """Dtype of a DataArray/array *without* materializing it.

    Calling ``.values`` here would pull the whole variable from the backing
    store -- fatal for a lazily-opened remote dataset.
    """
    dtype = getattr(obj, "dtype", None)
    return dtype if dtype is not None else np.asarray(obj).dtype


def _is_time(obj) -> bool:
    return np.issubdtype(_dtype_of(obj), np.datetime64)


def dap_type(obj) -> str:
    """DAP2 type name (datetimes are exposed as Float64 epoch)."""
    if _is_time(obj):
        return "Float64"
    return _DAP_TYPES.get(_dtype_of(obj), "String")


_ERDDAP_TYPES = {
    "float32": "float",
    "float64": "double",
    "int8": "byte",
    "uint8": "ubyte",
    "int16": "short",
    "uint16": "ushort",
    "int32": "int",
    "uint32": "uint",
    "int64": "long",
    "uint64": "ulong",
}


def erddap_type(obj) -> str:
    """ERDDAP ``.json``/``info`` type name of a variable."""
    if _is_time(obj):
        return "double"
    return _ERDDAP_TYPES.get(_dtype_of(obj).name, "String")


def format_value(value, *, is_time: bool):
    """One cell as ERDDAP writes it; ``None`` for a missing number."""
    if is_time:
        ts = pd.Timestamp(value)
        if ts is pd.NaT:
            return ""
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, np.floating | float):
        if np.isnan(value):
            return None
        return _shortest_float(value)
    if isinstance(value, np.integer | int):
        return int(value)
    return value


def _shortest_float(value) -> float:
    """The float ERDDAP prints: the shortest repr *at the value's precision*.

    ``float(np.float32(19.225))`` is ``19.225000381469727``; ERDDAP writes
    ``19.225``, as Java's ``Float.toString`` does.
    """
    if isinstance(value, np.float32 | np.float16):
        return float(str(value))
    return float(value)


def java_number(value, *, das: bool = False) -> str:
    """A number as ERDDAP writes it, i.e. as Java's ``toString`` does.

    Shortest digits at the value's own precision; scientific notation below
    1e-3 and from 1e7 up (``4.734288E8``, ``-1.0E34``). The DAS spells the
    exponent the C way (``4.734288e+8``).
    """
    if isinstance(value, bool | np.bool_):
        return str(value).lower()
    if isinstance(value, int | np.integer):
        return str(int(value))
    x = value if isinstance(value, np.floating) else np.float64(value)
    if np.isnan(x):
        return "NaN"
    if np.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0 or 1e-3 <= abs(x) < 1e7:  # noqa: PLR2004
        return np.format_float_positional(x, unique=True, trim="0")
    text = np.format_float_scientific(x, unique=True, trim="0", exp_digits=1)
    return text if das else text.replace("e+", "E").replace("e-", "E-")


def attr_array(value) -> np.ndarray | None:
    """A numeric attribute as an array in its ERDDAP type; None for text.

    Plain Python ints are ERDDAP ``int``s, not ``long``s.
    """
    if isinstance(value, str | bytes | bool | np.bool_):
        return None
    arr = np.asarray(value)
    if arr.dtype.kind not in "fiu":
        return None
    if not isinstance(value, np.ndarray | np.generic) and arr.dtype.kind == "i":
        arr = arr.astype("int32")
    return arr.ravel()


def attr_type(value) -> str:
    """ERDDAP type name of an attribute value (``String`` for text)."""
    arr = attr_array(value)
    return "String" if arr is None else _ERDDAP_TYPES.get(arr.dtype.name, "double")


def sort_globals(names) -> list[str]:
    """ERDDAP's order for attributes: alphabetical, ignoring case.

    rerddap's ``info()`` reads ``time_coverage_end``/``_start`` positionally,
    so this order is load-bearing.
    """
    return sorted(names, key=lambda k: (k.lower(), k))


def attr_text(value, *, sep: str = ", ", das: bool = False) -> str:
    """Render an attribute value the way ERDDAP writes it in text responses.

    Sequences become ``"a, b"`` -- not Python's ``"[a, b]"``. rerddap parses
    ``actual_range`` numerically and silently yields NAs on the bracketed form.
    NcML separates with spaces instead.
    """
    arr = attr_array(value)
    if arr is None:
        return str(value)
    return sep.join(java_number(v, das=das) for v in arr)


def units_of(ed, name: str) -> str:
    """Units string ERDDAP would show for a variable."""
    if _is_time(ed.ds[name]):
        return "UTC"
    return attr_text(ed.variable_attrs(name).get("units", ""))


# --------------------------------------------------------------------------
# DDS / DAS
# --------------------------------------------------------------------------


def dds_response(
    ed,
    sub: xr.Dataset,
    variables: list[str],
    *,
    all_axes: bool = False,
) -> str:
    """ERDDAP-flavoured DDS for a (possibly subset) dataset.

    Like ERDDAP, the axes are listed on their own only for the whole dataset
    (``all_axes``) or when requested by name; a data request lists its GRIDs.
    """
    lines = ["Dataset {"]
    for dim in ed.dims:
        if not all_axes and dim not in variables:
            continue
        n = sub.sizes[dim]
        lines.append(f"  {dap_type(sub[dim])} {dim}[{dim} = {n}];")

    for name in variables:
        if name in ed.dims:
            continue
        da = sub[name]
        shape = "".join(f"[{d} = {sub.sizes[d]}]" for d in da.dims)
        lines.append("  GRID {")
        lines.append("    ARRAY:")
        lines.append(f"      {dap_type(da)} {name}{shape};")
        lines.append("    MAPS:")
        for d in da.dims:
            lines.append(
                f"      {dap_type(sub[d])} {d}[{d} = {sub.sizes[d]}];",
            )
        lines.append(f"  }} {name};")
    lines.append(f"}} {ed.dataset_id};")
    return "\n".join(lines) + "\n"


def _das_attr_lines(attrs: dict, indent: str) -> list[str]:
    out = []
    for key, value in attrs.items():
        arr = attr_array(value)
        if arr is None:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            out.append(f'{indent}String {key} "{escaped}";')
            continue
        dap = _DAP_TYPES.get(arr.dtype, "Float64")
        out.append(f"{indent}{dap} {key} {attr_text(arr, das=True)};")
    return out


def das_response(ed, sub: xr.Dataset) -> str:
    """ERDDAP-flavoured DAS."""
    lines = ["Attributes {"]
    for name in list(ed.dims) + [v for v in ed.data_vars if v in sub]:
        attrs = dict(ed.variable_attrs(name))
        if _is_time(ed.ds[name]):
            attrs["units"] = TIME_UNITS
            attrs.setdefault("_CoordinateAxisType", "Time")
            attrs.pop("_FillValue", None)  # ERDDAP rejects NaN fill on axes
            attrs.pop("calendar", None)
        lines.append(f"  {name} {{")
        lines.extend(_das_attr_lines(attrs, "    "))
        lines.append("  }")
    lines.append("  NC_GLOBAL {")
    lines.extend(
        _das_attr_lines({k: ed.globals_[k] for k in sort_globals(ed.globals_)}, "    "),
    )
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Tabular responses (ERDDAP flattens grids to long form)
# --------------------------------------------------------------------------


def _long_form(ed, sub: xr.Dataset, variables: list[str]):
    """Yield (column_names, units, types, row_iterator) in ERDDAP's long form."""
    axis_names = [d for d in ed.dims if d in sub.dims]
    value_names = [v for v in variables if v not in ed.dims]

    if not value_names:
        # a bare axis request, e.g. "?time"
        cols = [v for v in variables if v in ed.dims] or axis_names
        units = [units_of(ed, c) for c in cols]
        types = [erddap_type(sub[c]) for c in cols]
        times = [_is_time(sub[c]) for c in cols]
        arrays = [np.asarray(sub[c].values) for c in cols]

        def rows():
            # ERDDAP lists each axis in its own column, side by side, padding
            # the shorter ones with blanks -- not their cartesian product
            for tup in itertools.zip_longest(*arrays, fillvalue=None):
                yield [
                    "" if v is None else format_value(v, is_time=is_t)
                    for v, is_t in zip(tup, times, strict=True)
                ]

        return cols, units, types, rows()

    cols = axis_names + value_names
    units = [units_of(ed, c) for c in cols]
    types = [erddap_type(sub[c]) for c in cols]
    times = [_is_time(sub[c]) for c in cols]
    axis_values = [np.asarray(sub[a].values) for a in axis_names]
    stacked = [
        np.asarray(sub[v].transpose(*axis_names).values).ravel() for v in value_names
    ]

    def rows():
        for i, combo in enumerate(itertools.product(*axis_values)):
            row = list(combo) + [arr[i] for arr in stacked]
            yield [
                format_value(v, is_time=is_t)
                for v, is_t in zip(row, times, strict=True)
            ]

    return cols, units, types, rows()


def to_csv(ed, sub: xr.Dataset, variables: list[str], style: str = "csv") -> str:
    """ERDDAP ``.csv`` / ``.csvp`` / ``.csv0``.

    ``csv`` has a names row then a units row; ``csvp`` puts units in
    parentheses in the header; ``csv0`` has no header at all.
    """
    cols, units, _types, rows = _long_form(ed, sub, variables)
    buf = io.StringIO()
    if style == "csvp":
        header = [f"{c} ({u})" if u else c for c, u in zip(cols, units, strict=True)]
        buf.write(",".join(header) + "\n")
    elif style == "csv":
        buf.write(",".join(cols) + "\n")
        buf.write(",".join(units) + "\n")
    for row in rows:
        buf.write(",".join(_csv_value(v) for v in row) + "\n")
    return buf.getvalue()


def _csv_value(value) -> str:
    if value is None:
        return "NaN"
    if isinstance(value, float):
        return java_number(value)
    return str(value)


def to_erddap_json(ed, sub: xr.Dataset, variables: list[str]) -> str:
    """ERDDAP's ``.json`` table structure."""
    cols, units, types, rows = _long_form(ed, sub, variables)
    # ERDDAP's JSON gives times as ISO strings and types the column to match
    types = ["String" if u == "UTC" else t for t, u in zip(types, units, strict=True)]
    payload = {
        "table": {
            "columnNames": cols,
            "columnTypes": types,
            "columnUnits": units,
            "rows": [[None if v == "" else v for v in row] for row in rows],
        },
    }
    return json.dumps(payload, indent=2, default=str)


def to_netcdf_bytes(ed, sub: xr.Dataset, variables: list[str]) -> bytes:
    """Serialize a subset to netCDF-3, with ERDDAP's subset metadata.

    Like ERDDAP, the coverage globals and each axis's ``actual_range``
    describe the subset, in the axis's dtype; axes carry no ``_FillValue``;
    time is float64 epoch seconds with ``units`` spelled with a ``Z``.
    """
    keep = [v for v in variables if v not in ed.dims]
    out = sub[keep] if keep else sub
    out = out.copy()
    out.attrs = {**ed.globals_, **coverage_globals(out, ed.dims, subset=True)}
    # the netCDF-4 library's stamp; ERDDAP lists it but does not write it
    out.attrs.pop("_NCProperties", None)
    encoding = {}
    for name in list(out.variables):
        # fill values travel in .encoding; xarray refuses them in both places
        attrs = {
            k: v
            for k, v in ed.variable_attrs(name).items()
            if k not in ("_FillValue", "missing_value")
        }
        if name not in ed.dims:
            out[name].attrs = attrs
            continue
        encoding[name] = {"_FillValue": None}
        values = np.asarray(out[name].values)
        if _is_time(out[name]):
            values = (values - np.datetime64(0, "s")) / np.timedelta64(1, "s")
            attrs.pop("calendar", None)
            attrs["units"] = TIME_UNITS
        if values.size:
            attrs["actual_range"] = np.array(
                [np.nanmin(values), np.nanmax(values)],
                dtype=values.dtype,
            )
        out = out.assign_coords({name: (name, values, attrs)})
    # Pin the engine: xarray's default for an in-memory write depends on which
    # backends happen to be installed, which is not reproducible. scipy writes
    # netCDF-3 classic, which is also what ERDDAP returns for ".nc".
    return out.to_netcdf(encoding=encoding, engine="scipy")


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _ncml_attr_lines(attrs: dict, indent: str) -> list[str]:
    out = []
    for key in sort_globals(attrs):
        value = attrs[key]
        kind = attr_type(value)
        typed = "" if kind == "String" else f' type="{kind}"'
        text = _xml_escape(attr_text(value, sep=" "))
        out.append(
            f'{indent}<attribute name="{_xml_escape(key)}"{typed} value="{text}" />',
        )
    return out


def _axis_attrs(ed, name: str) -> dict:
    """An axis's attributes as ERDDAP lists them (time in epoch seconds)."""
    attrs = dict(ed.variable_attrs(name))
    if _is_time(ed.ds[name]):
        attrs["units"] = TIME_UNITS
        attrs.pop("calendar", None)
    return attrs


def ncml_response(ed, location: str) -> str:
    """ERDDAP's ``.ncml`` metadata response.

    Global attributes sit directly under ``<netcdf>``, then the dimensions,
    then the variables; non-String attributes carry ``type=``. ``erddapy`` >=
    3.2 needs, for every dimension, a matching ``<variable>`` with a
    space-separated ``actual_range`` -- it raises if one is missing.

    ``location`` is the dataset's griddap URL. (ERDDAP itself drops the
    ``/erddap`` path segment there; we give the working URL.)
    """
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<netcdf xmlns="{NCML_NS}" location="{_xml_escape(location)}">',
    ]
    out.extend(_ncml_attr_lines(ed.globals_, "  "))
    for dim in ed.dims:
        out.append(
            f'  <dimension name="{_xml_escape(dim)}" length="{ed.ds.sizes[dim]}" />',
        )
    for name in list(ed.dims) + list(ed.data_vars):
        shape = " ".join(str(d) for d in ed.ds[name].dims)
        out.append(
            f'  <variable name="{_xml_escape(name)}" '
            f'shape="{_xml_escape(shape)}" '
            f'type="{erddap_type(ed.ds[name])}">',
        )
        attrs = _axis_attrs(ed, name) if name in ed.dims else ed.variable_attrs(name)
        out.extend(_ncml_attr_lines(attrs, "    "))
        out.append("  </variable>")
    out.append("</netcdf>")
    return "\n".join(out) + "\n"


def _spacing(values: np.ndarray) -> str:
    """ERDDAP's ``evenlySpaced=..., averageSpacing=...`` for an axis.

    The average is (last - first) / (n - 1), so it is negative for a
    descending axis. Float32 values are first rounded to 7 significant
    digits, as ERDDAP does (checked against real servers). Times are given
    as a duration, ``30 days 10h 27m 16s``.
    """
    if values.size < 2:  # noqa: PLR2004
        return ""
    if np.issubdtype(values.dtype, np.datetime64):
        numeric = (values - np.datetime64(0, "s")) / np.timedelta64(1, "s")
        tolerance = 1e-9
    else:
        numeric = nice_doubles(values)
        tolerance = 1e-5 if values.dtype == np.float32 else 1e-9
    average = (numeric[-1] - numeric[0]) / (numeric.size - 1)
    even = bool(np.all(np.abs(np.diff(numeric) - average) <= tolerance * abs(average)))
    if np.issubdtype(values.dtype, np.datetime64):
        spacing = _duration(average)
    else:
        spacing = java_number(average)
    return f", evenlySpaced={str(even).lower()}, averageSpacing={spacing}"


def _duration(seconds: float) -> str:
    """A time step the way ERDDAP writes it: ``1 day 0h 6m 4s``."""
    sign = "-" if seconds < 0 else ""
    total = round(abs(seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    hms = f"{hours}h {minutes}m {secs}s"
    if days:
        unit = "day" if days == 1 else "days"
        return f"{sign}{days} {unit} {hms}"
    return sign + hms


def info_table(ed) -> tuple[list[str], list[list]]:
    """Rows for ``/info/{id}/index.csv``.

    Matches ERDDAP's five-column layout, which erddapy and rerddap both parse.
    """
    columns = ["Row Type", "Variable Name", "Attribute Name", "Data Type", "Value"]
    rows: list[list] = []

    def attribute_rows(owner: str, attrs: dict) -> None:
        for key in sort_globals(attrs):
            value = attrs[key]
            rows.append(["attribute", owner, key, attr_type(value), attr_text(value)])

    attribute_rows("NC_GLOBAL", ed.globals_)
    for dim in ed.dims:
        values = np.asarray(ed.ds[dim].values)
        rows.append(
            [
                "dimension",
                dim,
                "",
                erddap_type(ed.ds[dim]),
                f"nValues={values.size}{_spacing(values)}",
            ],
        )
        attribute_rows(dim, _axis_attrs(ed, dim))
    for name in ed.data_vars:
        dims = ", ".join(str(d) for d in ed.ds[name].dims)
        rows.append(["variable", name, "", erddap_type(ed.ds[name]), dims])
        attribute_rows(name, ed.variable_attrs(name))
    return columns, rows
