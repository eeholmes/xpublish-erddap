"""ERDDAP-compatible router for Xpublish.

Serves the subset of ERDDAP's griddap REST API that `erddapy` and `rerddap`
actually call, so existing client code works unchanged against an Xpublish
server. The HTML interfaces (Data Access Form, Make-A-Graph) are out of scope.

ERDDAP is catalog-oriented -- clients point at one server root holding many
flat datasetIDs -- so this is an ``app_router``, not a ``dataset_router``.
"""

from __future__ import annotations

import io
import json
import logging
from urllib import parse

import xarray as xr
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from xpublish import Dependencies, Plugin, hookimpl

from xpublish_erddap import formats
from xpublish_erddap.catalog import (
    ErddapDataset,
    build_catalog,
    tree_datasets,
    unique_ids,
)
from xpublish_erddap.constraints import ConstraintError, parse_griddap_query

logger = logging.getLogger("uvicorn")

#: rerddap asserts on this exact string, so it must not gain a space.
ERDDAP_JSON = "application/json;charset=UTF-8"

TABULAR = {"csv", "csvp", "csv0", "json"}

#: File types of the catalog, info and search tables.
TABLE_EXTENSIONS = {"csv", "json"}
ALL_EXTENSIONS = TABULAR | {"nc", "ncml", "das", "dds"}

#: Recognised but not served yet. Kept out of ALL_EXTENSIONS so no error
#: message advertises them, but answered with 501 and a pointer instead of
#: the generic "unsupported" 400. ``.dods`` will reuse xpublish-opendap's
#: encoder (issue #2); until then, OPeNDAP clients should use the store's
#: OPeNDAP endpoint.
PLANNED_EXTENSIONS = {
    "dods": (
        "OPeNDAP binary (.dods) is planned but not implemented yet "
        "(https://github.com/eeholmes/xpublish-erddap/issues/2). "
        "For OPeNDAP access, use the dataset's OPeNDAP endpoint instead."
    ),
}


def _resolve(request: Request, dep, *args):
    """Call one of the ``deps`` xpublish gave the router, outside FastAPI's DI.

    An app router has no ``{dataset_id}`` in its path, so it cannot use
    ``Depends(deps.dataset)``; it calls the function itself. ``xpublish.Rest``
    passes its real getters, which are called directly. Default
    ``Dependencies()`` hold xpublish's placeholder getters, which an app fills
    in through ``dependency_overrides``, so look there first.
    """
    fn = request.app.dependency_overrides.get(dep, dep)
    return fn(*args)


def erddap_root(request: Request, prefix: str) -> str:
    """The public URL of this ERDDAP root, for URLs we hand to clients.

    The app may sit below a path prefix: mounted inside another app (a
    per-store service such as ``.../regrid/main/erddap``) or behind a proxy
    started with ``--root-path``. Starlette puts that prefix in ``root_path``
    in both cases, but ``request.base_url`` includes it only in the second.
    """
    root_path = request.scope.get("root_path", "").rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}{root_path}{prefix}"


#: ERDDAP counts megabytes in units of 2**20 bytes (``Math2.BytesPerMB``).
BYTES_PER_MB = 2**20

#: Real ERDDAP servers refuse a ``.nc`` response over 2 GB; we copy that.
NC_LIMIT_MB = 2 * 1024


def estimated_bytes(ds: xr.Dataset, variables: list[str], selections) -> int:
    """Size of the requested values in bytes, computed before reading any data.

    Each requested variable counts its selected cells times its itemsize. Text
    responses (csv, json) are several times larger than this; ``.nc`` is close.
    """
    total = 0
    for name in variables:
        var = ds[name]
        cells = 1
        for dim in var.dims:
            cells *= selections[dim].size if dim in selections else var.sizes[dim]
        total += cells * formats._dtype_of(var).itemsize  # noqa: SLF001
    return total


def too_much_data(size_mb: int, limit: str) -> HTTPException:
    """ERDDAP's 413, with its message wording (captured from coastwatch.pfeg)."""
    return HTTPException(
        413,
        "Payload Too Large: Your query produced too much data.  "
        f"Try to request less data. [memory]  {size_mb} MB is more than {limit}.",
    )


def check_size(ds: xr.Dataset, parsed, ext: str, limit_mb: float | None) -> None:
    """Refuse a data request over the server's limit, or a ``.nc`` over 2 GB."""
    size = estimated_bytes(ds, parsed.variables, parsed.selections)
    size_mb = round(size / BYTES_PER_MB)
    if limit_mb is not None and size > limit_mb * BYTES_PER_MB:
        raise too_much_data(size_mb, f"this server's {limit_mb:g} MB limit")
    if ext == "nc" and size > NC_LIMIT_MB * BYTES_PER_MB:
        raise too_much_data(size_mb, "the .nc 2 GB limit")


class ErddapPlugin(Plugin):
    """ERDDAP griddap API plugin for Xpublish."""

    name: str = "erddap"

    app_router_prefix: str = "/erddap"
    app_router_tags: list[str] = ["erddap"]

    #: Global attributes merged into every dataset (ERDDAP's ``addAttributes``).
    metadata: dict = {}

    #: Drop datasets whose axes are not strictly monotonic, as ERDDAP does.
    strict_axes: bool = True

    #: Refuse a data request (nc, csv, json, ...) whose values would exceed
    #: this many MB, before reading any data. ``None`` means no limit beyond
    #: the 2 GB ``.nc`` cap copied from real ERDDAP servers. Responses are
    #: built in memory, so a public server should set this.
    max_response_mb: float | None = None

    @hookimpl
    def app_router(self, deps: Dependencies) -> APIRouter:  # noqa: PLR0915
        """Create the ERDDAP router.

        All routes live on one router because ERDDAP's catalog endpoints and
        its data endpoints share the catalog/lookup closures.
        """
        router = APIRouter(prefix=self.app_router_prefix, tags=self.app_router_tags)
        plugin = self

        # -- catalog ----------------------------------------------------
        def catalog(request: Request) -> dict[str, ErddapDataset]:
            cache = _resolve(request, deps.cache)
            key = "erddap_catalog"
            found = cache.get(key) if cache is not None else None
            if found is not None:
                return found
            entries: list[ErddapDataset] = []
            for xpublish_id in _resolve(request, deps.dataset_ids):
                tree = _resolve(request, deps.datatree, xpublish_id)
                for source_id, ds in tree_datasets(xpublish_id, tree):
                    entries += build_catalog(
                        source_id,
                        ds,
                        metadata=plugin.metadata,
                        strict_axes=plugin.strict_axes,
                    )
            out = unique_ids(entries)
            if cache is not None:
                cache.put(key, out, 99999)
            return out

        def lookup(request: Request, dataset_id: str) -> ErddapDataset:
            cat = catalog(request)
            if dataset_id not in cat:
                raise HTTPException(
                    404,
                    f"datasetID {dataset_id!r} not found. "
                    f"Available: {', '.join(sorted(cat)) or '(none)'}",
                )
            return cat[dataset_id]

        def raw_query(request: Request) -> str:
            """ERDDAP queries are raw expressions, not key=value pairs.

            erddapy percent-encodes with ``quote_plus``, so decode with
            ``unquote_plus``.
            """
            return parse.unquote_plus(request.url.components[3])

        def _table(columns, rows, ext: str, name: str) -> Response:
            if ext not in TABLE_EXTENSIONS:
                # ERDDAP answers 404 for an unknown table fileType
                raise HTTPException(
                    404,
                    f"Unsupported fileType=.{ext}; use "
                    f"{', '.join('.' + e for e in sorted(TABLE_EXTENSIONS))}",
                )
            if ext == "json":
                # rerddap asserts this exact content-type string
                return Response(
                    json.dumps(
                        {
                            "table": {
                                "columnNames": columns,
                                "columnTypes": ["String"] * len(columns),
                                "rows": rows,
                            },
                        },
                        indent=2,
                        default=str,
                    ),
                    media_type=ERDDAP_JSON,
                )
            buf = io.StringIO()
            buf.write(",".join(columns) + "\n")
            for row in rows:
                buf.write(",".join(_csv_cell(v) for v in row) + "\n")
            return PlainTextResponse(buf.getvalue(), media_type="text/csv")

        def _csv_cell(value) -> str:
            # ERDDAP writes a newline inside a value as the two characters \n
            text = "" if value is None else str(value).replace("\n", "\\n")
            if any(c in text for c in ',"'):
                return '"' + text.replace('"', '""') + '"'
            return text

        # -- server metadata --------------------------------------------
        @router.get("/version", response_class=PlainTextResponse)
        def version() -> str:
            """ERDDAP version banner."""
            return "ERDDAP_version=2.23\n"

        @router.get("/griddap/index.{ext}")
        @router.get("/info/index.{ext}")
        def dataset_index(request: Request, ext: str) -> Response:
            """List every griddap dataset on the server."""
            cat = catalog(request)
            columns = [
                "griddap",
                "Info",
                "Institution",
                "Title",
                "Summary",
                "Dataset ID",
            ]
            base = erddap_root(request, plugin.app_router_prefix)
            rows = [
                [
                    f"{base}/griddap/{d.dataset_id}",
                    f"{base}/info/{d.dataset_id}/index.json",
                    str(d.globals_.get("institution", "")),
                    str(d.globals_.get("title", d.dataset_id)),
                    str(d.globals_.get("summary", "")),
                    d.dataset_id,
                ]
                for d in cat.values()
            ]
            return _table(columns, rows, ext, "datasets")

        @router.get("/tabledap/index.{ext}")
        def tabledap_index(request: Request, ext: str) -> Response:  # noqa: ARG001
            """Empty tabledap catalog.

            rerddap calls this to decide whether a datasetID is tabledap or
            griddap, so it must answer with a well-formed (if empty) table
            rather than a 404.
            """
            return _table(
                ["griddap", "Info", "Institution", "Title", "Summary", "Dataset ID"],
                [],
                ext,
                "tabledap",
            )

        @router.get("/info/{dataset_id}/index.{ext}")
        def dataset_info(request: Request, dataset_id: str, ext: str) -> Response:
            """Variable and attribute table for one dataset."""
            ed = lookup(request, dataset_id)
            columns, rows = formats.info_table(ed)
            return _table(columns, rows, ext, dataset_id)

        @router.get("/search/index.{ext}")
        def search(request: Request, ext: str, searchFor: str = "") -> Response:  # noqa: N803
            """Free-text search across dataset metadata."""
            if not searchFor.split():
                raise HTTPException(
                    404,
                    f"A .{ext} search request must include a query, for "
                    'example, "?page=1&itemsPerPage=1000&searchFor=wind+temperature".',
                )
            return _search(request, ext, searchFor)

        @router.get("/search/advanced.{ext}")
        def advanced_search(
            request: Request,
            ext: str,
            searchFor: str = "",  # noqa: N803
        ) -> Response:
            """Advanced search. Only ``searchFor`` filters so far (#4).

            As in ERDDAP, the request needs at least one criterion: erddapy
            sends every field, with ``(ANY)`` or an empty value for those
            not in use, and ``protocol=griddap`` counts as one.
            """
            criteria = [
                value
                for key, value in request.query_params.items()
                if key not in {"page", "itemsPerPage"}
                and value.strip() not in {"", "(ANY)"}
            ]
            if not criteria:
                raise HTTPException(
                    400,
                    f"Query error: A .{ext} Advanced Search request must include "
                    "one or more criteria, for example, "
                    '"?page=1&itemsPerPage=1000&searchFor=wind+temperature".',
                )
            return _search(request, ext, searchFor)

        def _search(request: Request, ext: str, searchFor: str) -> Response:  # noqa: N803
            cat = catalog(request)
            terms = searchFor.lower().split()
            # ERDDAP's special case: "all" on its own lists every dataset.
            if terms == ["all"]:
                terms = []
            base = erddap_root(request, plugin.app_router_prefix)
            rows = []
            for d in cat.values():
                blob = " ".join(
                    [
                        d.dataset_id,
                        *[f"{k} {v}" for k, v in d.globals_.items()],
                        *d.data_vars,
                    ],
                ).lower()
                if terms and not all(t in blob for t in terms):
                    continue
                rows.append(
                    [
                        "griddap",
                        f"{base}/griddap/{d.dataset_id}",
                        f"{base}/info/{d.dataset_id}/index.json",
                        str(d.globals_.get("title", d.dataset_id)),
                        str(d.globals_.get("summary", "")),
                        d.dataset_id,
                    ],
                )
            if not rows:
                raise HTTPException(
                    404,
                    f"Your query produced no matching results: {searchFor!r}",
                )
            columns = [
                "protocol",
                "griddap",
                "Info",
                "Title",
                "Summary",
                "Dataset ID",
            ]
            return _table(columns, rows, ext, "search")

        # -- data --------------------------------------------------------
        @router.get("/griddap/{target}")
        def griddap(request: Request, target: str) -> Response:
            """Serve a griddap request: ``{datasetID}.{fileType}?{query}``."""
            if "." not in target:
                raise HTTPException(
                    400,
                    f"missing fileType: use {target}.<type>, one of "
                    f"{', '.join(sorted(ALL_EXTENSIONS))}",
                )
            dataset_id, _, ext = target.rpartition(".")
            if ext in PLANNED_EXTENSIONS:
                raise HTTPException(501, PLANNED_EXTENSIONS[ext])
            if ext not in ALL_EXTENSIONS:
                raise HTTPException(
                    400,
                    f"unsupported fileType {ext!r}; "
                    f"this server supports {', '.join(sorted(ALL_EXTENSIONS))}",
                )
            ed = lookup(request, dataset_id)
            query = raw_query(request)

            if ext == "das":
                return PlainTextResponse(formats.das_response(ed, ed.ds))
            if ext == "ncml":
                base = erddap_root(request, plugin.app_router_prefix)
                return Response(
                    formats.ncml_response(ed, f"{base}/griddap/{dataset_id}"),
                    media_type="application/xml",
                )

            try:
                parsed = parse_griddap_query(
                    query,
                    ed.axes,
                    list(ed.dims),
                    list(ed.data_vars),
                )
            except ConstraintError as exc:
                raise HTTPException(400, str(exc)) from exc

            if ext != "dds":
                check_size(ed.ds, parsed, ext, plugin.max_response_mb)

            indexers = {d: sel.as_slice() for d, sel in parsed.selections.items()}
            sub: xr.Dataset = ed.ds.isel(indexers)

            if ext == "dds":
                return PlainTextResponse(
                    formats.dds_response(
                        ed,
                        sub,
                        parsed.variables,
                        all_axes=not query.strip(),
                    ),
                )
            if ext == "nc":
                data = formats.to_netcdf_bytes(ed, sub, parsed.variables)
                return Response(
                    data,
                    media_type="application/x-netcdf",
                    headers={
                        "Content-Disposition": (
                            f'attachment; filename="{dataset_id}.nc"'
                        ),
                    },
                )
            if ext == "json":
                return Response(
                    formats.to_erddap_json(ed, sub, parsed.variables),
                    media_type=ERDDAP_JSON,
                )
            if ext in {"csv", "csvp", "csv0"}:
                return PlainTextResponse(
                    formats.to_csv(ed, sub, parsed.variables, style=ext),
                    media_type="text/csv",
                )
            # every ALL_EXTENSIONS member is handled above
            raise AssertionError(ext)  # pragma: no cover

        return router
