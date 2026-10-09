"""ERDDAP-compatible routers for Xpublish.

Serves the subset of ERDDAP's griddap REST API that `erddapy` and `rerddap`
actually call, so existing client code works unchanged against an Xpublish
server. The HTML interfaces (Data Access Form, Make-A-Graph) are out of scope.

ERDDAP is catalog-oriented -- clients point at one server root holding many
flat datasetIDs -- so the main router is a server-wide ``app_router``; a
``dataset_router`` serves the same API for one dataset or group (see
``docs/hosting.md``).
"""

from __future__ import annotations

import html
import inspect
import io
import json
import logging
import time
from collections.abc import Callable
from urllib import parse

import xarray as xr
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from xpublish import Dependencies, Plugin, hookimpl
from xpublish.dependencies import get_group_path
from xpublish.utils.api import DATASET_ID_ATTR_KEY

from xpublish_erddap import formats, search
from xpublish_erddap.catalog import (
    ErddapDataset,
    build_catalog,
    tree_datasets,
    unique_ids,
)
from xpublish_erddap.constraints import ConstraintError, NoMatchError, parse_griddap_query
from xpublish_erddap.errors import ErddapRoute

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

    The ASGI path is decoded, so a group called ``my group`` would give a URL
    with a space in it; the path is percent-encoded again here.
    """
    root_path = request.scope.get("root_path", "").rstrip("/")
    path = parse.quote(f"{root_path}{prefix}")
    return f"{request.url.scheme}://{request.url.netloc}{path}"


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
    """ERDDAP's 413, with its message wording (captured from coastwatch.pfeg).

    The "Payload Too Large: " prefix is added with the rest of the error body.
    """
    return HTTPException(
        413,
        "Your query produced too much data.  "
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


# -- helpers the routes share ------------------------------------------------
# They take the catalog and the public base URL instead of a request, so any
# router that can produce those (the server-wide one, a per-dataset one) can
# use them.


def lookup(catalog: dict[str, ErddapDataset], dataset_id: str) -> ErddapDataset:
    """One dataset from the catalog, or ERDDAP's 404."""
    if dataset_id not in catalog:
        # ERDDAP's wording (coastwatch.noaa.gov, 2026-10-07)
        raise HTTPException(404, f"Currently unknown datasetID={dataset_id}")
    return catalog[dataset_id]


def raw_query(request: Request) -> str:
    """ERDDAP queries are raw expressions, not key=value pairs.

    erddapy percent-encodes with ``quote_plus``, so decode with
    ``unquote_plus``.
    """
    return parse.unquote_plus(request.url.components[3])


_JSON_ESCAPES = {"\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": ""}


def csv_cell(value: object) -> str:
    r"""One csv field, quoted the way ERDDAP quotes it.

    A port of ERDDAP's ``String2.toSVString(s, 127)``: text with a control
    character, comma, backslash, quote, a character from 127 up, or a
    leading or trailing space is JSON-encoded (``toJson``: ``\n``, and
    ``\u00b0`` for a degree sign, so the file is plain ASCII), and then
    ``\"`` becomes ``""``.
    """
    text = "" if value is None else str(value)
    needs_json = any(c in ',\\"' or not 32 <= ord(c) < 127 for c in text)  # noqa: PLR2004
    if not needs_json and not text.startswith(" ") and not text.endswith(" "):
        return text
    out = []
    # Java strings are UTF-16: a character past U+FFFF is two \u escapes
    for unit in _utf16_units(text):
        c = chr(unit)
        if unit < 32 or unit >= 127:  # noqa: PLR2004
            out.append(_JSON_ESCAPES.get(c, f"\\u{unit:04x}"))
        elif c in '\\"':
            out.append("\\" + c)
        else:
            out.append(c)
    return '"' + "".join(out).replace('\\"', '""') + '"'


def _utf16_units(text: str) -> list[int]:
    data = text.encode("utf-16-be", "surrogatepass")
    return [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]


def table_response(columns: list[str], rows: list[list], ext: str) -> Response:
    """A catalog, info or search table as ``.csv`` or ``.json``."""
    if ext not in TABLE_EXTENSIONS:
        # ERDDAP answers 404 for an unknown table fileType, in these words
        raise HTTPException(404, f"Unsupported fileType=.{ext}")
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


def query_params(request: Request) -> dict[str, str]:
    """The query's parameters, the first value winning as in ERDDAP's servlets."""
    return dict(reversed(request.query_params.multi_items()))


def index_response(
    catalog: dict[str, ErddapDataset],
    base: str,
    ext: str,
    params: dict[str, str],
) -> Response:
    """ERDDAP's table of every griddap dataset, by title (``griddap/index``)."""
    found = search.page_of(search.by_title(list(catalog.values())), params)
    rows = [search.dataset_row(d, base, ext) for d in found]
    return table_response(search.DATASET_COLUMNS, rows, ext)


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


def info_page(ed: ErddapDataset, base: str) -> HTMLResponse:
    """A minimal ``info/{id}/index.html``: the title and links to the data.

    There is no UI, but rerddapXtracto's ``safe_info()`` and rerddap's
    ``browse()`` request this URL and need a page that exists (#62).
    """
    title = html.escape(str(ed.globals_.get("title", ed.dataset_id)))
    links = [
        (f"{base}/info/{ed.dataset_id}/index.{kind}", f"Variables and attributes ({kind})")
        for kind in sorted(TABLE_EXTENSIONS)
    ] + [
        (f"{base}/griddap/{ed.dataset_id}.{kind}", f"Data access: {ed.dataset_id}.{kind}")
        for kind in ("das", "dds")
    ]
    items = "\n".join(
        f'<li><a href="{html.escape(url)}">{html.escape(text)}</a></li>' for url, text in links
    )
    return HTMLResponse(
        f"<!DOCTYPE html>\n<html><head><title>{title}</title></head>\n"
        f"<body><h1>{title}</h1>\n<ul>\n{items}\n</ul></body></html>\n",
    )


def search_response(
    found: list[ErddapDataset],
    base: str,
    ext: str,
    no_match: HTTPException,
) -> Response:
    """ERDDAP's dataset table for search results, or ``no_match`` if there are none.

    ERDDAP words "no matches" differently for a plain and an advanced search.
    """
    if not found:
        raise no_match
    rows = [search.dataset_row(d, base, ext) for d in found]
    return table_response(search.DATASET_COLUMNS, rows, ext)


def split_target(target: str) -> tuple[str, str]:
    """``{datasetID}.{fileType}`` -> (datasetID, fileType), refusing bad types."""
    if "." not in target:
        raise HTTPException(
            400,
            f"missing fileType: use {target}.<type>, one of {', '.join(sorted(ALL_EXTENSIONS))}",
        )
    dataset_id, _, ext = target.rpartition(".")
    if ext in PLANNED_EXTENSIONS:
        raise HTTPException(501, PLANNED_EXTENSIONS[ext])
    if ext not in ALL_EXTENSIONS:
        # ERDDAP's wording (coastwatch.noaa.gov, 2026-10-07)
        raise HTTPException(400, f"Query error: fileType=.{ext} isn't supported by this dataset.")
    return dataset_id, ext


def griddap_response(  # noqa: PLR0911, PLR0913
    ed: ErddapDataset,
    ext: str,
    query: str,
    base: str,
    max_response_mb: float | None,
    *,
    head: bool = False,
) -> Response:
    """Answer a griddap request for one dataset in one file type.

    ``head`` answers a HEAD request: the request is validated as for GET, but
    a data file (nc, json, csv...) is not built, only its headers sent.
    """
    if ext == "das":
        # ERDDAP's DAS is ISO-8859-1 (a degree sign is one byte); Java writes
        # a character outside it as "?"
        return Response(
            formats.das_response(ed, ed.ds).encode("latin-1", "replace"),
            media_type="text/plain;charset=ISO-8859-1",
        )
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
    except NoMatchError as exc:
        raise HTTPException(404, str(exc)) from exc
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
    if head and ext in HEAD_MEDIA:
        return Response(media_type=HEAD_MEDIA[ext])
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


#: Content types of the data files, for a HEAD request that builds none.
HEAD_MEDIA = {
    "nc": "application/x-netcdf",
    "json": ERDDAP_JSON,
    "csv": "text/csv",
    "csvp": "text/csv",
    "csv0": "text/csv",
}


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
CATEGORIZE = "/categorize/index.{ext}"
CATEGORIZE_ATTRIBUTE = "/categorize/{attribute}/index.{ext}"
CATEGORIZE_VALUE = "/categorize/{attribute}/{value}/index.{ext}"
GRIDDAP = "/griddap/{target}"

#: Path parameters of the routes above, plus the host's group path: any other
#: path parameter names the dataset.
ROUTE_PARAMS = {"ext", "erddap_id", "target", "group_path", "attribute", "value"}


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


def categorize_attributes(request: Request, ext: str) -> Response:
    """``categorize/index.{ext}``: ERDDAP's ``categorizeOptionsTable``."""
    _, per_page = search.page_params(query_params(request))
    base = f"{root_of(request, CATEGORIZE)}/categorize"
    names = list(search.CATEGORY_ATTRIBUTES)
    return table_response(*search.category_table("Categorize", names, base, ext, per_page), ext)


def categorize_values(
    request: Request,
    attribute: str,
    ext: str,
    catalog: dict[str, ErddapDataset],
) -> Response:
    """``categorize/{attribute}/index.{ext}``: ERDDAP's ``sendCategoryPftOptionsTable``.

    Every value, however many; ``page`` and ``itemsPerPage`` do not apply (they
    are only passed on in the URLs).
    """
    if attribute not in search.CATEGORY_ATTRIBUTES:
        raise HTTPException(404, "")  # ERDDAP: "Not Found: (no details)"
    _, per_page = search.page_params(query_params(request))
    base = f"{root_of(request, CATEGORIZE_ATTRIBUTE)}/categorize/{attribute}"
    values = search.category_values(list(catalog.values()), attribute)
    return table_response(*search.category_table("Category", values, base, ext, per_page), ext)


def categorize_datasets(
    request: Request,
    attribute: str,
    value: str,
    ext: str,
    catalog: dict[str, ErddapDataset],
) -> Response:
    """``categorize/{attribute}/{value}/index.{ext}``: the dataset table.

    A value that no dataset has is a 404 with no details, unless its lower-case
    form has datasets: ERDDAP redirects there. Paged like a search.
    """
    if attribute not in search.CATEGORY_ATTRIBUTES:
        raise HTTPException(404, "")
    datasets = list(catalog.values())
    matching = search.category_datasets(datasets, attribute, value)
    params = query_params(request)
    base = root_of(request, CATEGORIZE_VALUE)
    if not matching:
        lower = value.lower()
        if value == lower or not search.category_datasets(datasets, attribute, lower):
            raise HTTPException(404, "")
        _, per_page = search.page_params(params)
        return RedirectResponse(
            f"{base}/categorize/{attribute}/{parse.quote(lower)}/"
            f"index.{ext}?page=1&itemsPerPage={per_page}",
            status_code=302,
        )
    found = search.page_of(matching, params)
    return search_response(found, base, ext, search.no_matches())


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

    def route(path: str, **kwargs):
        # ERDDAP answers HEAD like GET (rerddapXtracto's safe_info(), erddapy's
        # check_url_response()); the data route skips building its body.
        return router.api_route(path, methods=["GET", "HEAD"], **kwargs)

    @route(VERSION, response_class=PlainTextResponse)
    def version() -> str:
        """ERDDAP version banner."""
        return "ERDDAP_version=2.23\n"

    @route(GRIDDAP_INDEX)
    def griddap_index(
        request: Request,
        ext: str,
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """List every griddap dataset under this root."""
        return index_response(
            cat,
            root_of(request, GRIDDAP_INDEX),
            ext,
            query_params(request),
        )

    @route(INFO_INDEX)
    def info_index(
        request: Request,
        ext: str,
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """The same list, as ERDDAP serves it under ``info``."""
        return index_response(
            cat,
            root_of(request, INFO_INDEX),
            ext,
            query_params(request),
        )

    @route(TABLEDAP_INDEX)
    def tabledap_index(ext: str) -> Response:
        """Empty tabledap catalog.

        rerddap calls this to decide whether a datasetID is tabledap or
        griddap, so it must answer with a well-formed (if empty) table
        rather than a 404.
        """
        return table_response(search.DATASET_COLUMNS, [], ext)

    @route(INFO)
    def dataset_info(
        request: Request,
        erddap_id: str,
        ext: str,
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """Variable and attribute table for one dataset."""
        ed = lookup(cat, erddap_id)
        if ext == "html":
            return info_page(ed, root_of(request, INFO))
        return table_response(*formats.info_table(ed), ext)

    @route(SEARCH)
    def search_index(
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
        params = query_params(request)
        found = search.page_of(search.text_search(list(cat.values()), searchFor), params)
        return search_response(
            found,
            root_of(request, SEARCH),
            ext,
            search.no_search_matches(searchFor),
        )

    @route(ADVANCED_SEARCH)
    def advanced_search(
        request: Request,
        ext: str,
        searchFor: str = "",  # noqa: N803
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """Advanced search: protocol, categories, bounds, then ``searchFor`` (#4)."""
        advanced_search_criteria(request, ext)
        params = query_params(request)
        matching = search.advanced_filter(list(cat.values()), params)
        found = search.page_of(search.text_search(matching, searchFor), params)
        return search_response(found, root_of(request, ADVANCED_SEARCH), ext, search.no_matches())

    @route(CATEGORIZE)
    def categorize_index(request: Request, ext: str) -> Response:
        """The category attributes to browse by (``Erddap.doCategorize``, #5)."""
        return categorize_attributes(request, ext)

    @route(CATEGORIZE_ATTRIBUTE)
    def categorize_attribute(
        request: Request,
        attribute: str,
        ext: str,
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """The values of one category attribute, with the URL of each."""
        return categorize_values(request, attribute, ext, cat)

    @route(CATEGORIZE_VALUE)
    def categorize_value(
        request: Request,
        attribute: str,
        value: str,
        ext: str,
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """The datasets with one category value, by title (the dataset table)."""
        return categorize_datasets(request, attribute, value, ext, cat)

    @route(GRIDDAP)
    def griddap(
        request: Request,
        target: str,
        cat: Catalog = Depends(catalog),
    ) -> Response:
        """Serve a griddap request: ``{datasetID}.{fileType}?{query}``."""
        dataset_id, ext = split_target(target)
        return griddap_response(
            lookup(cat, dataset_id),
            ext,
            raw_query(request),
            root_of(request, GRIDDAP),
            max_response_mb,
            head=request.method == "HEAD",
        )

    return router


def name_from_path(params: dict[str, str], group: str) -> str:
    """The default ``ErddapPlugin.name_dataset``: dataset path parameters, then group.

    ``params`` are the URL's path parameters that name the dataset, in path
    order: ``{"dataset_id": "sst"}`` under ``xpublish.Rest``, ``{}`` under
    ``SingleDatasetRest``, ``{"org": ..., "repo": ..., "ref": ...}`` in a
    Flux-like host. They are joined with ``/``, or ``dataset`` if there are
    none, and the group path is appended. Under ``Rest`` this gives the same
    datasetIDs as the server-wide root. The result goes through the usual
    datasetID rule (``sanitize_id``, a suffix per dimension split).
    """
    name = "/".join(params.values()) or "dataset"
    return f"{name}/{group}" if group else name


#: cachey eviction cost for catalogs, as xpublish's own plugins use: high, so
#: they are evicted last. It is not a lifetime.
CACHE_COST = 99999


def catalog_nbytes(entries) -> int:
    """About how much memory ``entries`` (a list or dict of datasets) hold.

    Axis values plus a rough 200 B per attribute. Without it cachey counts a
    catalog as ~56 B, when it is ~0.1 MB, and never evicts it.
    """
    nbytes = 1024
    for entry in entries.values() if isinstance(entries, dict) else entries:
        nbytes += sum(axis.nbytes for axis in entry.axes.values())
        nbytes += 200 * (
            len(entry.globals_) + sum(len(entry.ds[name].attrs) + 1 for name in entry.ds.variables)
        )
    return nbytes


def memo(cache, key: str, stamp: object, build: Callable[[], object]) -> object:
    """``build()``, cached under ``key`` until ``stamp`` changes.

    One entry per key, replaced when the stamp changes, so superseded catalogs
    (and the datasets they hold) are not kept. cachey is told the catalog's
    size, not left to guess it.
    """
    hit = cache.get(key) if cache is not None else None
    if hit is not None and hit[0] == stamp:
        return hit[1]
    value = build()
    if cache is not None:
        cache.put(key, (stamp, value), CACHE_COST, nbytes=catalog_nbytes(value))
    return value


def tree_version(tree: xr.DataTree) -> str | None:
    """The ``_xpublish_id`` of ``tree``: its own, else its root's.

    xpublish core and xpublish-tiles key their caches on it, and Earthmover
    Flux sets it to ``{org}/{repo}/{snapshot}/{group}``, so it changes with
    every commit. ``xpublish.Rest`` sets it to the dataset id when the
    provider has not set it.
    """
    return tree.attrs.get(DATASET_ID_ATTR_KEY) or tree.root.attrs.get(
        DATASET_ID_ATTR_KEY,
    )


def has_server_root(deps: Dependencies) -> bool:
    """Whether a server-wide root can work: ``deps.datatree`` takes one dataset id.

    Under ``xpublish.SingleDatasetRest`` it takes none, and dataset routers are
    mounted at the app root, where they would collide with the app router. A
    host that names a dataset with several path parameters (Flux:
    ``{org}/{repo}/{ref}``) cannot be asked for a dataset by one id either.

    An ``async def`` ``datatree`` also rules it out: the server-wide root calls
    it directly, from a worker thread, where it would only return an unawaited
    coroutine. The per-dataset root hands it to FastAPI, which awaits it, so
    that root works.
    """
    if inspect.iscoroutinefunction(deps.datatree):
        return False
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

    #: Serve latitude, longitude and time axes under ERDDAP's names
    #: (``latitude``, ``longitude``, ``time``), which clients such as plotdap
    #: read by name. ``False`` keeps the source names; a dict maps source axis
    #: names to served names instead of recognising them (``{"lat":
    #: "latitude"}``). Names ERDDAP cannot serve (``sst-anom``) are made safe
    #: either way. See ``catalog.served_names`` and ``docs/hosting.md``.
    rename_axes: bool | dict[str, str] = True

    #: Refuse a data request (nc, csv, json, ...) whose values would exceed
    #: this many MB, before reading any data, with ERDDAP's 413. Responses are
    #: built in memory, so the default is a finite 500. ERDDAP has no fixed
    #: default of its own: it refuses what would not fit in 75% of the JVM's
    #: heap (``Math2.ensureMemoryAvailable``) and any ``.nc`` over about 2 GB
    #: (``EDDGrid.saveAsNc``). ``None`` means no limit beyond that 2 GB ``.nc``
    #: cap; use it only where a whole-variable request is safe.
    max_response_mb: float | None = 500

    #: How a per-dataset root names its dataset, before the datasetID rule:
    #: ``name_dataset(params, group) -> str``, where ``params`` are the URL's
    #: path parameters that name the dataset and ``group`` the group path
    #: (``""`` for none). The default is ``name_from_path``. A host whose
    #: path does not suit it (see ``docs/hosting.md``) passes its own; under
    #: ``SingleDatasetRest``, e.g. ``lambda params, group: "sst"``. The
    #: server-wide root is not affected: it names by xpublish dataset id.
    name_dataset: Callable[[dict[str, str], str], str] = name_from_path

    #: Rebuild a catalog at least this often, in seconds, even if the data's
    #: ``_xpublish_id`` has not changed. ``None`` (the default) rebuilds only
    #: when it changes. For hosts whose data changes in place (a Zarr store
    #: appended to under a fixed id); see ``docs/hosting.md``.
    catalog_max_age_s: float | None = None

    def build(self, source_id: str, tree: xr.DataTree) -> list[ErddapDataset]:
        """ERDDAP datasets for every group with variables in ``tree``."""
        entries: list[ErddapDataset] = []
        for group_id, ds in tree_datasets(source_id, tree):
            entries += build_catalog(
                group_id,
                ds,
                metadata=self.metadata,
                strict_axes=self.strict_axes,
                rename_axes=self.rename_axes,
            )
        return entries

    def stamp(self, tree: xr.DataTree) -> tuple:
        """What a cached catalog of ``tree`` is valid for (#3).

        Its ``_xpublish_id``, and with ``catalog_max_age_s`` the current
        period of that length, so a catalog is rebuilt when either changes.
        """
        period = 0
        if self.catalog_max_age_s:
            period = int(time.time() // self.catalog_max_age_s)
        return (tree_version(tree), period)

    def entries(
        self,
        cache,
        source_id: str,
        tree: xr.DataTree,
        key: str | None = None,
    ) -> list[ErddapDataset]:
        """``build(source_id, tree)``, cached while ``tree``'s stamp holds.

        Cached under ``key``, default ``source_id``: the server-wide root uses
        the xpublish dataset id, a per-dataset root the URL's identity (#61),
        since ``name_dataset`` may give two groups, or two refs, one name.
        """
        return memo(
            cache,
            f"erddap_entries/{key or source_id}",
            self.stamp(tree),
            lambda: self.build(source_id, tree),
        )

    def server_catalog(
        self,
        request: Request,
        deps: Dependencies,
    ) -> dict[str, ErddapDataset]:
        """Every group of every published dataset, by ERDDAP datasetID (cached).

        Each request asks the host for every dataset's current tree, to see
        whether any has changed; only changed ones are rebuilt.
        """
        cache = _resolve(request, deps.cache)
        stamps, entries = [], []
        for xpublish_id in _resolve(request, deps.dataset_ids):
            # One source that cannot be opened or built must not take the
            # others down (ERDDAP keeps serving the datasets that loaded). It
            # is left out, and tried again on the next request, so it returns
            # as soon as it heals; it does not keep a last good entry (#56).
            try:
                tree = _resolve(request, deps.datatree, xpublish_id)
                stamp = self.stamp(tree)
                built = self.entries(cache, xpublish_id, tree)
            except Exception as exc:  # noqa: BLE001 -- includes HTTPException
                logger.warning(
                    "ERDDAP: leaving dataset %r out of the server-wide catalog -- %s: %s",
                    xpublish_id,
                    type(exc).__name__,
                    getattr(exc, "detail", None) or exc,
                )
                continue
            stamps.append((xpublish_id, stamp))
            entries += built
        return memo(cache, "erddap_catalog", tuple(stamps), lambda: unique_ids(entries))

    @hookimpl
    def app_router(self, deps: Dependencies) -> APIRouter:
        """The server-wide ERDDAP root: one catalog of every dataset."""
        router = APIRouter(
            prefix=self.app_router_prefix,
            tags=self.app_router_tags,
            route_class=ErddapRoute,
        )
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
            prefix=self.dataset_router_prefix,
            tags=self.dataset_router_tags,
            route_class=ErddapRoute,
        )

        def catalog(
            request: Request,
            tree: xr.DataTree = Depends(deps.datatree),
            cache=Depends(deps.cache),
        ) -> dict[str, ErddapDataset]:
            params = {
                key: str(value)
                for key, value in request.path_params.items()
                if key not in ROUTE_PARAMS
            }
            group = get_group_path(request)
            source_id = self.name_dataset(params, group)
            # Keyed on what the URL names, never on name_dataset's result,
            # which a host may make blind to the group or the ref (#61).
            key = "/".join([*(f"{k}={v}" for k, v in params.items()), group])
            entries = self.entries(cache, source_id, tree, f"url/{key}")
            return memo(
                cache,
                f"erddap_catalog/url/{key}",
                self.stamp(tree),
                lambda: unique_ids(entries),
            )

        return add_erddap_routes(router, catalog, self.max_response_mb)
