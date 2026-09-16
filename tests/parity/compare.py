"""Normalise and compare a real ERDDAP response with ours.

Only differences that cannot and should not match are normalised away: the
server's own URL, and the request timestamps ERDDAP appends to ``history``.
Everything else is compared as the client receives it.
"""

from __future__ import annotations

import io
import json
import math
import re

import numpy as np
import xarray as xr

#: Lines ERDDAP appends to ``history`` on every request, e.g.
#: ``2026-09-16T19:44:40Z (local files)`` and
#: ``2026-09-16T19:44:40Z https://server/erddap/griddap/id.das``.
_REQUEST_HISTORY = re.compile(
    r"(?:\\n|\n)?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ (?:\(local files\)|https?://\S+?)"
    r"(?=\\n|\n|\"|$)",
)


def normalise_text(text: str, server: str) -> str:
    """Strip per-request history lines and replace the server URL."""
    text = _REQUEST_HISTORY.sub("", text)
    root = server.rstrip("/")
    text = text.replace(root, "{SERVER}")
    # ERDDAP's NcML ``location`` drops the ``/erddap`` path segment
    host_root = root.rsplit("/erddap", 1)[0]
    return text.replace(host_root, "{SERVER}")


def media_type(content_type: str | None) -> str:
    """The media type without parameters such as ``charset``."""
    return (content_type or "").split(";", 1)[0].strip()


def comparable(body: bytes, ext: str, server: str):
    """Turn a response body into the value we compare, by file type."""
    if ext == "nc":
        return _netcdf_summary(body, server)
    text = normalise_text(body.decode("utf-8", "replace"), server)
    if ext == "json":
        return json.loads(text)
    return text


def ext_of(path: str) -> str:
    """File type of a request path (``griddap/x.csv?...`` -> ``csv``)."""
    return path.split("?", 1)[0].rsplit(".", 1)[-1]


def _netcdf_summary(body: bytes, server: str) -> dict:
    """What a client sees in a netCDF file, raw (no CF decoding)."""
    with xr.open_dataset(io.BytesIO(body), decode_cf=False) as ds:
        variables = {}
        for name, var in ds.variables.items():
            variables[name] = {
                "dims": list(var.dims),
                "dtype": str(var.dtype),
                "attrs": _attrs(var.attrs, server),
                "values": _nan_to_none(var.values.tolist()),
            }
        return {
            "dims": dict(ds.sizes),
            "attrs": _attrs(ds.attrs, server),
            "variables": variables,
        }


def _attrs(attrs: dict, server: str) -> dict:
    out = {}
    for key, value in attrs.items():
        if isinstance(value, str):
            out[key] = normalise_text(value, server)
        else:
            arr = np.asarray(value)
            out[key] = [str(arr.dtype), _nan_to_none(arr.tolist())]
    return out


def _nan_to_none(value):
    """NaN never equals NaN; make it comparable."""
    if isinstance(value, list):
        return [_nan_to_none(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
