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
from xpublish.dependencies import get_cache as _cache_dep
from xpublish.dependencies import get_dataset as _dataset_dep
from xpublish.dependencies import get_dataset_ids as _dataset_ids_dep

from xpublish_erddap import formats
from xpublish_erddap.catalog import ErddapDataset, build_catalog
from xpublish_erddap.constraints import ConstraintError, parse_griddap_query

logger = logging.getLogger("uvicorn")

#: rerddap asserts on this exact string, so it must not gain a space.
ERDDAP_JSON = "application/json;charset=UTF-8"

TABULAR = {"csv", "csvp", "csv0", "json"}
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
    """Call an xpublish dependency through the app's overrides."""
    fn = request.app.dependency_overrides.get(dep, dep)
    return fn(*args)


class ErddapPlugin(Plugin):
    """ERDDAP griddap API plugin for Xpublish."""

    name: str = "erddap"

    app_router_prefix: str = "/erddap"
    app_router_tags: list[str] = ["erddap"]

    #: Global attributes merged into every dataset (ERDDAP's ``addAttributes``).
    metadata: dict = {}

    #: Drop datasets whose axes are not strictly monotonic, as ERDDAP does.
    strict_axes: bool = True

    @hookimpl
    def app_router(self, deps: Dependencies) -> APIRouter:  # noqa: ARG002, PLR0915
        """Create the ERDDAP router.

        All routes live on one router because ERDDAP's catalog endpoints and
        its data endpoints share the catalog/lookup closures.
        """
        router = APIRouter(prefix=self.app_router_prefix, tags=self.app_router_tags)
        plugin = self

        # -- catalog ----------------------------------------------------
        def catalog(request: Request) -> dict[str, ErddapDataset]:
            cache = _resolve(request, _cache_dep)
            key = "erddap_catalog"
            found = cache.get(key) if cache is not None else None
            if found is not None:
                return found
            out: dict[str, ErddapDataset] = {}
            for source_id in _resolve(request, _dataset_ids_dep):
                ds = _resolve(request, _dataset_dep, source_id)
                entries = build_catalog(
                    source_id,
                    ds,
                    metadata=plugin.metadata,
                    strict_axes=plugin.strict_axes,
                )
                for entry in entries:
                    out[entry.dataset_id] = entry
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
            base = str(request.base_url).rstrip("/") + plugin.app_router_prefix
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
        @router.get("/search/advanced.{ext}")
        def search(request: Request, ext: str, searchFor: str = "") -> Response:  # noqa: N803
            """Free-text search across dataset metadata."""
            cat = catalog(request)
            terms = [t for t in searchFor.lower().split() if t]
            base = str(request.base_url).rstrip("/") + plugin.app_router_prefix
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
                    f"missing fileType: use {target}.nc, .csv, .json, .dds, .das",
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
                base = str(request.base_url).rstrip("/") + plugin.app_router_prefix
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
