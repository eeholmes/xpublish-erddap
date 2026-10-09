"""Normalise and compare a real ERDDAP response with ours.

Only differences that cannot and should not match are normalised away: the
server's own URL, and the request timestamps ERDDAP appends to ``history``.
Everything else is compared as the client receives it.
"""

from __future__ import annotations

import csv
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


def normalise_text(text: str, server: str | tuple[str, ...]) -> str:
    """Strip per-request history lines and replace the server URL.

    ``server`` may be several roots. Our side passes its own and the real
    server's: a dataset attribute that names the real server (``infoUrl``,
    ``publisher_url``, a license's citation link) is the dataset's own value,
    which we serve as it is, and the real side has that URL replaced too.
    """
    text = _REQUEST_HISTORY.sub("", text)
    # A dataset with no ``history`` of its own is given one by ERDDAP that
    # holds only the request lines; nothing is left of it once they are gone.
    text = re.sub(r'^ *String history "";\n', "", text, flags=re.MULTILINE)
    text = re.sub(r'^ *<attribute name="history" value="" />\n', "", text, flags=re.MULTILINE)
    for one in [server] if isinstance(server, str) else server:
        root = one.rstrip("/")
        text = text.replace(root, "{SERVER}")
        # ERDDAP's NcML ``location`` drops the ``/erddap`` path segment
        text = text.replace(root.rsplit("/erddap", 1)[0], "{SERVER}")
    return text


def media_type(content_type: str | None) -> str:
    """The media type without parameters such as ``charset``."""
    return (content_type or "").split(";", 1)[0].strip()


def comparable(body: bytes, ext: str, server: str | tuple[str, ...]):
    """Turn a response body into the value we compare, by file type."""
    if ext == "nc":
        return _netcdf_summary(body, server)
    text = normalise_text(body.decode("utf-8", "replace"), server)
    if ext == "json":
        return json.loads(text)
    return text


def lists(body: str, dataset_id: str) -> bool:
    """Whether a search response lists ``dataset_id``.

    A search lists the whole server's catalog, so its body cannot be compared
    with ours; whether it includes the case's dataset can.
    """
    return dataset_id in body


def ext_of(path: str) -> str:
    """File type of a request path (``griddap/x.csv?...`` -> ``csv``)."""
    return path.split("?", 1)[0].rsplit(".", 1)[-1]


def _netcdf_summary(body: bytes, server: str | tuple[str, ...]) -> dict:
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


def _attrs(attrs: dict, server: str | tuple[str, ...]) -> dict:
    out = {}
    for key, value in attrs.items():
        if isinstance(value, str):
            out[key] = normalise_text(value, server)
            if key == "history" and not out[key]:
                del out[key]  # only ERDDAP's request lines (see normalise_text)
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


#: Dataset-table columns that depend on the server's configuration, not the
#: dataset: ``Accessible`` (logins) and ``Email`` (subscriptions). We copy a
#: server with neither (#27), so they are left out of the comparison.
CONFIG_COLUMNS = {"Accessible", "Email"}

#: Dataset-table columns we fill. The rest link to services we do not offer
#: (Make A Graph, WMS, files, FGDC, ISO 19115, RSS) and are empty in ours.
COMPARED_COLUMNS = (
    "griddap",
    "Subset",
    "tabledap",
    "Title",
    "Summary",
    "Info",
    "Background Info",
    "Institution",
    "Dataset ID",
)


def _table(body: str, ext: str) -> tuple[list[str], list[list[str]]]:
    if ext == "json":
        table = json.loads(body)["table"]
        return table["columnNames"], [[str(v) for v in row] for row in table["rows"]]
    rows = list(csv.reader(io.StringIO(body)))
    return rows[0], rows[1:]


def dataset_table(body: bytes, ext: str, dataset_id: str, server: str | tuple[str, ...]) -> dict:
    """What we compare of ERDDAP's dataset table (search, griddap/index, ...).

    The header without the configuration columns, and the row for
    ``dataset_id`` in the columns we fill. The rest of the server's catalog
    cannot be compared with ours.
    """
    text = normalise_text(body.decode("utf-8", "replace"), server)
    header, rows = _table(text, ext)
    row = next((r for r in rows if r[header.index("Dataset ID")] == dataset_id), None)
    return {
        "header": [c for c in header if c not in CONFIG_COLUMNS],
        "row": None if row is None else {c: row[header.index(c)] for c in COMPARED_COLUMNS},
    }
