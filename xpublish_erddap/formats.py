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

__all__ = [
    "CONTENT_TYPES",
    "TIME_UNITS",
    "das_response",
    "dds_response",
    "format_value",
    "info_table",
    "to_csv",
    "to_erddap_json",
    "to_netcdf_bytes",
]

TIME_UNITS = "seconds since 1970-01-01T00:00:00Z"

CONTENT_TYPES = {
    "das": "text/plain",
    "dds": "text/plain",
    "csv": "text/csv",
    "csv0": "text/csv",
    "csvp": "text/csv",
    "tsv": "text/tab-separated-values",
    "json": "application/json",
    "nc": "application/x-netcdf",
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


def erddap_type(obj) -> str:
    """ERDDAP ``.json``/``info`` type name."""
    if _is_time(obj):
        return "double"
    return {
        "float32": "float",
        "float64": "double",
        "int8": "byte",
        "int16": "short",
        "int32": "int",
        "int64": "long",
    }.get(_dtype_of(obj).name, "String")


def format_value(value, *, is_time: bool):
    """Render one cell the way ERDDAP does."""
    if is_time:
        ts = pd.Timestamp(value)
        if ts is pd.NaT:
            return ""
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, (np.floating, float)):
        if np.isnan(value):
            return ""
        return float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    return value


def attr_text(value) -> str:
    """Render an attribute value the way ERDDAP writes it in text responses.

    Sequences become ``"a, b"`` -- not Python's ``"[a, b]"``. rerddap parses
    ``actual_range`` numerically and silently yields NAs on the bracketed form.
    """
    if isinstance(value, (list, tuple, np.ndarray)):
        return ", ".join(str(v) for v in np.asarray(value).ravel().tolist())
    if isinstance(value, (np.floating, np.integer)):
        return str(value.item())
    return str(value)


def units_of(ed, name: str) -> str:
    """Units string ERDDAP would show for a variable."""
    if _is_time(ed.ds[name]):
        return "UTC"
    return attr_text(ed.variable_attrs(name).get("units", ""))


# --------------------------------------------------------------------------
# DDS / DAS
# --------------------------------------------------------------------------

def dds_response(ed, sub: xr.Dataset, variables: list[str]) -> str:
    """ERDDAP-flavoured DDS for a (possibly subset) dataset."""
    lines = ["Dataset {"]
    for dim in ed.dims:
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
        if isinstance(value, (list, tuple, np.ndarray)):
            joined = ", ".join(str(v) for v in np.asarray(value).ravel())
            out.append(f'{indent}Float64 {key} {joined};')
        elif isinstance(value, (bool, np.bool_)):
            out.append(f'{indent}String {key} "{value}";')
        elif isinstance(value, (np.floating, float)):
            out.append(f"{indent}Float64 {key} {float(value)};")
        elif isinstance(value, (np.integer, int)):
            out.append(f"{indent}Int32 {key} {int(value)};")
        else:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            out.append(f'{indent}String {key} "{escaped}";')
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
        _das_attr_lines({k: ed.globals_[k] for k in sorted(ed.globals_)}, "    "),
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
            for tup in zip(*arrays, strict=True):
                yield [
                    format_value(v, is_time=is_t)
                    for v, is_t in zip(tup, times, strict=True)
                ]

        return cols, units, types, rows()

    cols = axis_names + value_names
    units = [units_of(ed, c) for c in cols]
    types = [erddap_type(sub[c]) for c in cols]
    times = [_is_time(sub[c]) for c in cols]
    axis_values = [np.asarray(sub[a].values) for a in axis_names]
    stacked = [
        np.asarray(sub[v].transpose(*axis_names).values).ravel()
        for v in value_names
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
        buf.write(",".join("" if v == "" else str(v) for v in row) + "\n")
    return buf.getvalue()


def to_erddap_json(ed, sub: xr.Dataset, variables: list[str]) -> str:
    """ERDDAP's ``.json`` table structure."""
    cols, units, types, rows = _long_form(ed, sub, variables)
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
    """Serialize to netCDF, with ERDDAP-style time encoding."""
    keep = [v for v in variables if v not in ed.dims]
    out = sub[keep] if keep else sub
    out = out.copy()
    out.attrs = dict(ed.globals_)
    for name in out.variables:
        out[name].attrs = {
            k: v for k, v in ed.variable_attrs(name).items() if k != "_FillValue"
        }
    encoding = {}
    for name in out.coords:
        if _is_time(out[name]):
            encoding[name] = {"units": TIME_UNITS, "dtype": "float64"}
            out[name].attrs.pop("units", None)
    return out.to_netcdf(encoding=encoding)


def info_table(ed) -> tuple[list[str], list[list]]:
    """Rows for ``/info/{id}/index.csv``.

    Matches ERDDAP's five-column layout, which erddapy and rerddap both parse.
    """
    columns = ["Row Type", "Variable Name", "Attribute Name", "Data Type", "Value"]
    rows: list[list] = []
    # ERDDAP emits NC_GLOBAL attributes in alphabetical order, and rerddap
    # depends on it: print.info() takes time_coverage_end/_start positionally.
    for key in sorted(ed.globals_):
        rows.append(
            ["attribute", "NC_GLOBAL", key, "String", attr_text(ed.globals_[key])],
        )
    for dim in ed.dims:
        values = ed.ds[dim].values
        n = len(values)
        rows.append(["dimension", dim, "", erddap_type(ed.ds[dim]), f"nValues={n}"])
        attrs = dict(ed.variable_attrs(dim))
        if _is_time(values):
            attrs["units"] = TIME_UNITS
        for key, value in attrs.items():
            rows.append(["attribute", dim, key, "String", attr_text(value)])
    for name in ed.data_vars:
        rows.append(["variable", name, "", erddap_type(ed.ds[name]), ""])
        for key, value in ed.variable_attrs(name).items():
            rows.append(["attribute", name, key, "String", attr_text(value)])
    return columns, rows
