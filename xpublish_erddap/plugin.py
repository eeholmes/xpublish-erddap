"""ERDDAP-compatible routers for Xpublish.

Serves the subset of ERDDAP's griddap REST API that `erddapy` and `rerddap`
actually call, so existing client code works unchanged against an Xpublish
server. The HTML interfaces (Data Access Form, Make-A-Graph) are out of scope.

ERDDAP is catalog-oriented -- clients point at one server root holding many
flat datasetIDs -- so this is an ``app_router``, not a ``dataset_router``.
"""

from __future__ import annotations

import inspect
import io
import json
from collections.abc import Callable
from urllib import parse

import xarray as xr
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from xpublish import Dependencies, Plugin, hookimpl
from xpublish.dependencies import get_group_path

from xpublish_erddap import formats
from xpublish_erddap.catalog import (
    ErddapDataset,
    build_catalog,
    tree_datasets,
    unique_ids,
)
from xpublish_erddap.constraints import ConstraintError, parse_griddap_query

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
        total += cells * formats.dtype_of(var).itemsize
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


#: Columns of the griddap/info catalog tables (and the empty tabledap one).
CATALOG_COLUMNS = ["griddap", "Info", "Institution", "Title", "Summary", "Dataset ID"]

#: Columns of the search results table.
SEARCH_COLUMNS = ["protocol", "griddap", "Info", "Title", "Summary", "Dataset ID"]


# -- helpers the routes share ------------------------------------------------
# They take the catalog and the public base URL instead of a request, so any
# router that can produce those (the server-wide one, a per-dataset one) can
# use them.


def lookup(catalog: dict[str, ErddapDataset], dataset_id: str) -> ErddapDataset:
    """One dataset from the catalog, or ERDDAP's 404."""
    if dataset_id not in catalog:
        raise HTTPException(
            404,
            f"datasetID {dataset_id!r} not found. "
            f"Available: {', '.join(sorted(catalog)) or '(none)'}",
        )
    return catalog[dataset_id]


def raw_query(request: Request) -> str:
    """ERDDAP queries are raw expressions, not key=value pairs.

    erddapy percent-encodes with ``quote_plus``, so decode with
    ``unquote_plus``.
    """
    return parse.unquote_plus(request.url.components[3])


def csv_cell(value: object) -> str:
    """One csv field, quoted the way ERDDAP quotes it."""
    # ERDDAP writes a newline inside a value as the two characters \n
    text = "" if value is None else str(value).replace("\n", "\\n")
    if any(c in text for c in ',"'):
        return '"' + text.replace('"', '""') + '"'
    return text


def table_response(columns: list[str], rows: list[list], ext: str) -> Response:
    """A catalog, info or search table as ``.csv`` or ``.json``."""
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
        buf.write(",".join(csv_cell(v) for v in row) + "\n")
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


def index_response(catalog: dict[str, ErddapDataset], base: str, ext: str) -> Response:
    """The table of every griddap dataset."""
    rows = [
        [
            f"{base}/griddap/{d.dataset_id}",
            f"{base}/info/{d.dataset_id}/index.json",
            str(d.globals_.get("institution", "")),
            str(d.globals_.get("title", d.dataset_id)),
            str(d.globals_.get("summary", "")),
            d.dataset_id,
        ]
        for d in catalog.values()
    ]
    return table_response(CATALOG_COLUMNS, rows, ext)


def advanced_search_criteria(request: Request, ext: str) -> None:
    """Refuse an advanced search with no criteria, as ERDDAP does.

    erddapy sends every field, with ``(ANY)`` or an empty value for those not
    in use, and ``protocol=griddap`` counts as one.
    """
    criteria = [
        value
        for key, value in request.query_params.items()
        if key not in {"page", "itemsPerPage"} and value.strip() not in {"", "(ANY)"}
    ]
    if not criteria:
        raise HTTPException(
            400,
            f"Query error: A .{ext} Advanced Search request must include "
            "one or more criteria, for example, "
            '"?page=1&itemsPerPage=1000&searchFor=wind+temperature".',
        )


def search_response(
    catalog: dict[str, ErddapDataset],
    base: str,
    ext: str,
    search_for: str,
) -> Response:
    """Datasets whose id, global attributes or variable names hold every term."""
    terms = search_for.lower().split()
    # ERDDAP's special case: "all" on its own lists every dataset.
    if terms == ["all"]:
        terms = []
    rows = []
    for d in catalog.values():
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
            f"Your query produced no matching results: {search_for!r}",
        )
    return table_response(SEARCH_COLUMNS, rows, ext)


def split_target(target: str) -> tuple[str, str]:
    """``{datasetID}.{fileType}`` -> (datasetID, fileType), refusing bad types."""
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
    return dataset_id, ext


def griddap_response(
    ed: ErddapDataset,
    ext: str,
    query: str,
    base: str,
    max_response_mb: float | None,
) -> Response:
    """Answer a griddap request for one dataset in one file type."""
    if ext == "das":
        return PlainTextResponse(formats.das_response(ed, ed.ds))
    if ext == "ncml":
        return Response(
            formats.ncml_response(ed, f"{base}/griddap/{ed.dataset_id}"),
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
        check_size(ed.ds, parsed, ext, max_response_mb)

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
                "Content-Disposition": (f'attachment; filename="{ed.dataset_id}.nc"'),
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


# -- the ERDDAP routes, shared by both routers -------------------------------
#: Route paths below an ERDDAP root. ``{erddap_id}`` is not ``{dataset_id}``,
#: which xpublish's own dataset prefix (``/datasets/{dataset_id}``) uses.
VERSION = "/version"
GRIDDAP_INDEX = "/griddap/index.{ext}"
INFO_INDEX = "/info/index.{ext}"
TABLEDAP_INDEX = "/tabledap/index.{ext}"
INFO = "/info/{erddap_id}/index.{ext}"
SEARCH = "/search/index.{ext}"
ADVANCED_SEARCH = "/search/advanced.{ext}"
GRIDDAP = "/griddap/{target}"

#: Path parameters of the routes above, plus the host's group path: any other
#: path parameter names the dataset.
ROUTE_PARAMS = {"ext", "erddap_id", "target", "group_path"}


def root_of(request: Request, route_path: str) -> str:
    """The public URL of the ERDDAP root that answered ``request``.

    The root's path is the request path less the route's own part
    (``route_path`` with this request's values): ``/erddap`` for the
    server-wide router, ``/datasets/a/erddap`` or a host's own prefix (Flux:
    ``.../{group path}/erddap``) for the per-dataset one. The matched route
    cannot say: under a dataset prefix it reports only the router's path.
    """
    path = request.scope["path"]
    root_path = request.scope.get("root_path", "")
    # Starlette includes a mount's root_path in "path"; erddap_root adds it.
    if root_path and path.startswith(root_path):
        path = path[len(root_path) :]
    own = route_path.format(**request.path_params)
    return erddap_root(request, path.removesuffix(own))


def add_erddap_routes(
    router: APIRouter,
    catalog: Callable[..., dict[str, ErddapDataset]],
    max_response_mb: float | None,
) -> APIRouter:
    """Declare the ERDDAP API on ``router``, serving ``catalog``.

    ``catalog`` is a FastAPI dependency returning the datasets this root
    serves, by datasetID.
    """
    Catalog = dict[str, ErddapDataset]  # noqa: N806

    @router.get(VERSION, response_class=PlainTextResponse)
    def version() -> str:
        """ERDDAP version banner."""
        return "ERDDAP_version=2.23\n"

    @router.get(GRIDDAP_INDEX)
    def griddap_index(
        request: Request, ext: str, cat: Catalog = Depends(catalog)
    ) -> Response:
        """List every griddap dataset under this root."""
        return index_response(cat, root_of(request, GRIDDAP_INDEX), ext)

    @router.get(INFO_INDEX)
    def info_index(
        request: Request, ext: str, cat: Catalog = Depends(catalog)
    ) -> Response:
        """The same list, as ERDDAP serves it under ``info``."""
        return index_response(cat, root_of(request, INFO_INDEX), ext)

    @router.get(TABLEDAP_INDEX)
    def tabledap_index(ext: str) -> Response:
        """Empty tabledap catalog.

        rerddap calls this to decide whether a datasetID is tabledap or
        griddap, so it must answer with a well-formed (if empty) table
        rather than a 404.
        """
        return table_response(CATALOG_COLUMNS, [], ext)

    @router.get(INFO)
    def dataset_info(
        erddap_id: str, ext: str, cat: Catalog = Depends(catalog)
    ) -> Response:
        """Variable and attribute table for one dataset."""
        return table_response(*formats.info_table(lookup(cat, erddap_id)), ext)

    @router.get(SEARCH)
    def search(
        request: Request,
        ext: str,
        searchFor: str = "",  # noqa: N803
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """Free-text search across dataset metadata."""
        if not searchFor.split():
            raise HTTPException(
                404,
                f"A .{ext} search request must include a query, for "
                'example, "?page=1&itemsPerPage=1000&searchFor=wind+temperature".',
            )
        return search_response(cat, root_of(request, SEARCH), ext, searchFor)

    @router.get(ADVANCED_SEARCH)
    def advanced_search(
        request: Request,
        ext: str,
        searchFor: str = "",  # noqa: N803
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """Advanced search. Only ``searchFor`` filters so far (#4)."""
        advanced_search_criteria(request, ext)
        return search_response(cat, root_of(request, ADVANCED_SEARCH), ext, searchFor)

    @router.get(GRIDDAP)
    def griddap(
        request: Request, target: str, cat: Catalog = Depends(catalog)
    ) -> Response:
        """Serve a griddap request: ``{datasetID}.{fileType}?{query}``."""
        dataset_id, ext = split_target(target)
        return griddap_response(
            lookup(cat, dataset_id),
            ext,
            raw_query(request),
            root_of(request, GRIDDAP),
            max_response_mb,
        )

    return router


def has_server_root(deps: Dependencies) -> bool:
    """Whether a server-wide root can work: ``deps.datatree`` takes one dataset id.

    Under ``xpublish.SingleDatasetRest`` it takes none, and dataset routers are
    mounted at the app root, where they would collide with the app router. A
    host that names a dataset with several path parameters (Flux:
    ``{org}/{repo}/{ref}``) cannot be asked for a dataset by one id either.
    """
    params = inspect.signature(deps.datatree).parameters.values()
    return sum(p.default is inspect.Parameter.empty for p in params) == 1


class ErddapPlugin(Plugin):
    """ERDDAP griddap API plugin for Xpublish.

    It adds two ERDDAP roots, which serve the same API:

    - ``/erddap`` (``app_router``): one root for the whole server, listing
      every group of every dataset, the way clients expect an ERDDAP server.
    - ``.../{dataset}/erddap`` (``dataset_router``): one root per dataset, or
      per group when the host puts a ``{group_path}`` in the path, as
      Earthmover Flux does beside each group's ``/opendap``. Under
      ``xpublish.SingleDatasetRest`` this one is at ``/erddap``, and the
      server-wide root steps aside (see ``has_server_root``).
    """

    name: str = "erddap"

    app_router_prefix: str = "/erddap"
    app_router_tags: list[str] = ["erddap"]

    dataset_router_prefix: str = "/erddap"
    dataset_router_tags: list[str] = ["erddap"]

    #: Global attributes merged into every dataset (ERDDAP's ``addAttributes``).
    metadata: dict = {}

    #: Drop datasets whose axes are not strictly monotonic, as ERDDAP does.
    strict_axes: bool = True

    #: Refuse a data request (nc, csv, json, ...) whose values would exceed
    #: this many MB, before reading any data. ``None`` means no limit beyond
    #: the 2 GB ``.nc`` cap copied from real ERDDAP servers. Responses are
    #: built in memory, so a public server should set this.
    max_response_mb: float | None = None

    #: The datasetID base in a per-dataset root whose URL names no dataset
    #: (``SingleDatasetRest``). Otherwise the base is the URL's own dataset
    #: path parameters: ``{dataset_id}`` under ``xpublish.Rest``,
    #: ``{org}/{repo}/{ref}`` in a Flux-like host. A group path is appended.
    default_dataset_id: str = "dataset"

    def build(self, source_id: str, tree: xr.DataTree) -> list[ErddapDataset]:
        """ERDDAP datasets for every group with variables in ``tree``."""
        entries: list[ErddapDataset] = []
        for group_id, ds in tree_datasets(source_id, tree):
            entries += build_catalog(
                group_id,
                ds,
                metadata=self.metadata,
                strict_axes=self.strict_axes,
            )
        return entries

    def server_catalog(
        self, request: Request, deps: Dependencies
    ) -> dict[str, ErddapDataset]:
        """Every group of every published dataset, by ERDDAP datasetID (cached)."""
        cache = _resolve(request, deps.cache)
        key = "erddap_catalog"
        found = cache.get(key) if cache is not None else None
        if found is not None:
            return found
        entries: list[ErddapDataset] = []
        for xpublish_id in _resolve(request, deps.dataset_ids):
            entries += self.build(
                xpublish_id, _resolve(request, deps.datatree, xpublish_id)
            )
        out = unique_ids(entries)
        if cache is not None:
            cache.put(key, out, 99999)
        return out

    @hookimpl
    def app_router(self, deps: Dependencies) -> APIRouter:
        """The server-wide ERDDAP root: one catalog of every dataset."""
        router = APIRouter(prefix=self.app_router_prefix, tags=self.app_router_tags)
        if not has_server_root(deps):
            # The dataset router answers at the same paths; see the class doc.
            return router

        def catalog(request: Request) -> dict[str, ErddapDataset]:
            return self.server_catalog(request, deps)

        return add_erddap_routes(router, catalog, self.max_response_mb)

    @hookimpl
    def dataset_router(self, deps: Dependencies) -> APIRouter:
        """A per-dataset ERDDAP root, listing that dataset or group only."""
        router = APIRouter(
            prefix=self.dataset_router_prefix, tags=self.dataset_router_tags
        )

        def catalog(
            request: Request,
            tree: xr.DataTree = Depends(deps.datatree),
            cache=Depends(deps.cache),
        ) -> dict[str, ErddapDataset]:
            # Same naming as the server-wide root: dataset id + group path.
            names = [
                str(value)
                for key, value in request.path_params.items()
                if key not in ROUTE_PARAMS
            ]
            source_id = "/".join(names) or self.default_dataset_id
            group = get_group_path(request)
            if group:
                source_id = f"{source_id}/{group}"
            key = f"erddap_catalog/{source_id}"
            found = cache.get(key) if cache is not None else None
            if found is not None:
                return found
            out = unique_ids(self.build(source_id, tree))
            if cache is not None:
                cache.put(key, out, 99999)
            return out

        return add_erddap_routes(router, catalog, self.max_response_mb)
