# Design decisions and how we got here

## How the project changed direction (2026-09-15)

1. **First question:** how does xpublish-opendap work, and what would ERDDAP
   need? Background is in opendap-background.md.
2. **First plan:** be *reachable from* ERDDAP. A real ERDDAP would read a DAP
   URL through `EDDGridFromDap`. **Dropped:** EH has no ERDDAP server and does
   not want to run one.
3. **Discovery:** EH's data is Icechunk on Arraylake, and it is already served
   over DAP2 by Earthmover Flux. Flux's DAP2 service is built on xpublish
   (`_xpublish_id` appears in its DAS). Measurements are in
   cefi-flux-findings.md.
4. **Current direction:** an xpublish plugin that serves the ERDDAP REST API
   directly, so erddapy/rerddap work with no ERDDAP server at all.

EH set the scope in these words:

> "goal is not a ERDDAP like UI, rather to have erddapy and rerddap code work.
> to be able to read in URLs with formatted in the ERDDAP way for subsetting etc."

So this package is **for client compatibility, not an ERDDAP replacement**.
There is no Data Access Form, no Make-A-Graph, no image output, and no tabledap
(issue #7 is the open question on tabledap). Do not let it grow into a full
ERDDAP.

## Structure, and the reasons for it

    xpublish_erddap/
      plugin.py       ErddapPlugin: a server-wide app_router and a per-dataset dataset_router
      catalog.py      one Dataset -> N ERDDAP datasets; metadata inference; check_axes
      constraints.py  ERDDAP griddap query -> integer (start, stop, stride)
      formats.py      nc csv csvp csv0 json das dds ncml
      errors.py       ERDDAP plain-text error bodies
      search.py       dataset table, ranked searchFor, advanced-search filters

- **`app_router` first (and now a `dataset_router` too, #18).** ERDDAP is organized around a catalog:
  clients point at one server root and address many flat datasetIDs. The
  datasetIDs do not map one-to-one onto xpublish dataset ids (see the split
  below), and with no `{dataset_id}` in the path `Depends(deps.dataset)`
  cannot be used. So the routes call the `deps` xpublish passes to
  `app_router` themselves (`plugin.py`, `_resolve`), first looking each one up
  in `app.dependency_overrides` in case it is one of xpublish's placeholder
  getters. Until #32 they called the module-level
  `xpublish.dependencies.get_dataset` and friends instead, which ignored a
  caller's own `Dependencies`, against xpublish's plugin guide.
- **Groups of a published DataTree are datasets (#33, EH's call 2026-10-06).**
  Since xpublish 0.5 everything published is a DataTree. The server-wide
  catalog walks each tree (`catalog.tree_datasets`, via `deps.datatree`), and
  every group with data variables becomes a source named by xpublish id plus
  group path: `store` + `native/monthly` gives `store_native_monthly`. The
  root keeps the plain id. A group carries the coordinates it inherits but
  only its own attributes, as when xarray opens one group. Before this, a
  store whose variables were all in groups gave an empty catalog, with no
  error. Two sources that sanitize to one datasetID are both refused with a
  logged error (`catalog.unique_ids`); before, the later one silently
  replaced the earlier. The per-group router beside Flux's `/opendap` is a
  separate piece of work (#18), at EH's request.
- **The per-dataset root (#18, 2026-10-07).** `dataset_router` serves the same
  routes (`add_erddap_routes`) with a catalog of one dataset's subtree, got
  through `Depends(deps.datatree)`, so a host's group routing reaches it
  untouched (xpublish-tiles does the same). Decisions, each reversible:
  - **DatasetIDs keep the server-wide rule:** the URL's dataset path
    parameters joined, then the group path. Under `Rest` that is
    `{dataset_id}`; in a Flux-like host every non-route path parameter, so
    `{org}/{repo}/{ref}` + group (`NOAA_PMEL_cefi_store_main_regrid_main`):
    long, and it carries the ref. Flux's real parameter names are unknown;
    revisit with Earthmover. No dataset in the URL (`SingleDatasetRest`):
    `"dataset"`. The rule is the default of `ErddapPlugin(name_dataset=...)`
    (`name_from_path`), so a host changes it with an argument, not a fork
    (EH, 2026-10-07). `docs/hosting.md` is the note for Earthmover listing
    every such choice.
  - **The server-wide root steps aside** unless `deps.datatree` takes exactly
    one required argument (`has_server_root`). Under `SingleDatasetRest` both
    routers would be at `/erddap`, and xpublish's `check_route_conflicts`
    refuses to build the app. In a host that names datasets with several
    parameters, the server-wide catalog cannot look a dataset up by one id.
  - **Cache key per root:** `erddap_catalog/{source id}`; the server-wide one
    stays `erddap_catalog`.
  - **Public URLs** come from the request path less the route's own part
    (`root_of`). The matched route's template cannot be used: under a dataset
    prefix FastAPI reports only the router's own path.
  - The route parameter for a datasetID in `/info/.../index.{ext}` is
    `{erddap_id}`, because `{dataset_id}` is xpublish's own.
  - `tests/flux_host.py` stands in for Flux's routing; a store's root group
    would need `.../{ref}//erddap` there, so only groups below it are tested.
- **Errors are ERDDAP's plain-text body (#36, 2026-10-07).** erddapy raises
  `HTTPError` with the whole body as its message and rerddap prints it, so
  users saw FastAPI's `{"detail": ...}`. `errors.py` ports
  `EDStatic.lowSendError` (status prefix, JSON-quoted message, newlines kept,
  `text/plain;charset=UTF-8`); `ErddapRoute` (route class on both routers, as
  ogc-core does; a plugin cannot add app-wide handlers) turns `HTTPException`,
  validation errors (400) and unexpected exceptions (logged, 500) into it.
  Fixed messages use ERDDAP's wording: `Currently unknown datasetID=x`,
  `Unsupported fileType=.x` (tables, 404), `Query error: fileType=.x isn't
  supported by this dataset.` (griddap, 400), search's no-match text with
  "Try using fewer search words." when the search has a space. Kept on
  purpose: our constraint-error wording, and 400 where ERDDAP says 404 for an
  out-of-range value or 500 for an unknown variable. Parity compares the full
  error text wherever the golden is ERDDAP's own body (all IOOS cases;
  OceanWatch's are proxy pages). Paths outside our routes (`/erddap/nope`)
  still get FastAPI's 404.
- **The dataset table and searches copy ERDDAP's source (#27, #4, 2026-10-07).**
  `search.py` ports, from github.com/ERDDAP/erddap `main`:
  `Erddap.makePlainDatasetTable` (columns), `EDD.extendedSummary` (the
  Summary column's variable list and where it is cut), `doAdvancedSearch`
  (filters), `LoadDatasets.categorize*Atts` (category values), and the
  default "original" search engine (`getSearchDatasetIDs`, `searchRank`,
  `searchString`). Things a future session would otherwise re-derive:
  - **Columns depend on the server's config**, so there is no single
    "ERDDAP's columns". coastwatch.noaa.gov/polarwatch: 15; +`Email` with
    subscriptions (oceanwatch, and ERDDAP's *default* `setup.xml`); +
    `Accessible` with logins (erddap.ioos.us: 17). **EH chose the 15**
    (CoastWatch is what the tutorials use; we have neither feature). Links to
    services we do not offer are empty, as ERDDAP leaves them for datasets
    those services cannot handle.
  - Parity compares the header without `Accessible`/`Email` and etopo5's row
    in the columns we fill (`parity/compare.py`, `dataset_table`).
  - **`searchFor=all etopo5` matches** (every dataset's search text starts
    with "all"). #19's test said 404; that was not checked against a server
    then. erddap.ioos.us returns 200; fixed and now a parity case.
  - Category filters match ERDDAP's cleaned values (file-name safe, lower
    case: `noaa_marine_geology_and_geophysics_mgg_`), not the attribute as
    written; a value no dataset has is a 404 naming the parameter.
  - A time bound drops a dataset with no time axis (etopo5), as ERDDAP does.
- **Catalog caching (#3, EH's call 2026-10-07).** A cached catalog is valid
  for one `_xpublish_id` (the tree's own, else its root's): both roots ask
  the host for the current tree each request and rebuild when the id changes
  (`ErddapPlugin.stamp`, `memo`). Why: it is xpublish's convention (core
  `dataset_info`, xpublish-tiles key on it), and Flux's id carries the
  snapshot, so commits show up with nothing Flux-specific. xpublish-opendap
  keys on the URL's dataset id and is stale the same way we were. Fallback
  for data changing under a fixed id: `catalog_max_age_s` (time buckets, off
  by default). Rejected for now: a `setDatasetFlag`-style endpoint (no auth,
  #8). One cache entry per key, replaced on change, so superseded catalogs and
  their datasets are released. Cost: the server-wide root asks for every
  dataset's tree each request. `deploy/server.py` pins stores at startup, so
  the test server still needs a restart for new commits.
- **Route handlers are module-level functions (#34).** `plugin.py`'s helpers
  (`lookup`, `table_response`, `index_response`, `search_response`,
  `split_target`, `griddap_response`, ...) take the catalog and the public
  base URL, not the router, and `app_router` only declares routes. This is so
  #18's per-dataset router can reuse them with its own catalog and prefix.
  The server-wide catalog is `ErddapPlugin.server_catalog`.
- **One source dataset can become several ERDDAP datasets.** In ERDDAP, every
  data variable in a dataset must use all of the dataset's axes, so a Zarr
  group whose variables have different dimensions has to be split.
  `build_catalog` groups variables by their dimension signature. The main
  dataset keeps the plain id. It is chosen by most variables, then **fewest
  dimensions**, then alphabetical order. Without the dimension-count rule, a
  tie gave the plain id to a 4-D cube and left the simple 3-D one named
  `mixed_time_lat_lon` (a live test found this). The other datasets get a
  suffix naming the extra dimension (`_z_l`, `_ct`, `_level`).
- **Metadata injection:** `ErddapPlugin(metadata={...})` is the counterpart of
  ERDDAP's `datasets.xml` `<addAttributes>`. The Icechunk store never has to
  carry ERDDAP-specific attributes. `ioos_category`, axis units and the ACDD
  coverage globals (`time_coverage_*`, `geospatial_*`) are derived.
- **Colons in ISO timestamps.** `constraints.py` splits selectors on `:` only
  outside parentheses, because ISO 8601 values contain colons.
- **Never materialize data just to learn its type.** The first CEFI run
  returned a 500: `dds_response` called `.values` to get a dtype and pulled an
  11869×815×341 array from Flux (413 Request Entity Too Large). `formats.dtype_of`
  reads `.dtype` instead. **A local tutorial dataset would never have shown
  this**, so always test against a lazily opened remote store.

## `strict_axes=True`: refuse data that is non-monotonic

The CEFI monthly store has six duplicated months appended to its time axis.
Serving it produced **wrong results with no error**. Coordinate-value requests
looked right, because nearest-match lands on the first occurrence, which is in
the clean part of the series. Index ranges that crossed the duplicate boundary
returned times that jump backwards:

    tos[387:1:393] -> 2025-04, 2025-05, 2025-06, 2025-01, 2025-02, 2025-03, 2025-04

Real ERDDAP would refuse to load this dataset, and so do we now. `check_axes()`
logs which axis failed, the index of the first break, and how many duplicates
there are. `strict_axes=False` turns the check off. The general lesson:
**xarray accepts data that ERDDAP clients cannot handle correctly, so the
serving layer has to validate.**

## Aligned with xpublish-community conventions (2026-09-16)

The goal is to **donate this package to xpublish-community**, so it follows
the plugin family's conventions (opendap, edr, wms, intake-provider all came
from the IOOS package skeleton; xpublish-zarr is the newer exception).

- **License is BSD-3-Clause, in `LICENSE.txt`. This is deliberate and
  overrides the NOAA Apache-2.0 default in EH's global instructions.** The
  plugin family uses BSD-3 throughout (core xpublish and xpublish-zarr are
  Apache-2.0). EH chose BSD-3 because of the donation goal. Do not "fix" it.
  The sibling repos still have the skeleton's unfilled
  `Copyright 2017 AUTHOR NAME`; ours names a real copyright holder.
- `setuptools_scm` versioning, with the siblings' `_version` import pattern.
- `MANIFEST.in`, `requirements-dev.txt`, `.pre-commit-config.yaml` and
  `noxfile.py` were added. **`.isort.cfg` was deliberately left out:** all four
  siblings have one, but it only sets `known_third_party`, and ruff ignores
  that once its `"I"` rule is on. It does nothing, so it is not a convention
  worth copying.
- CI follows their pattern: micromamba + conda-forge, 3 OSes × Python
  3.12–3.14, xpublish installed from git `main`, coverage sent to codecov.
  **The job has to be named `run`,** because `noxfile.py` reads
  `jobs.run.strategy.matrix`.
- There is an **additional Linux-only `rerddap` job**; EH accepted this. R is
  a first-class target, but installing it on every job in the matrix costs
  more than it is worth. The server and the R client run in **one step**:
  a process started in the background in an earlier step is gone by the next
  step. The client connects to `127.0.0.1`, not `0.0.0.0` (0.0.0.0 is only
  valid as a bind address).
- The siblings' live-server test pattern (`pytest-xprocess`) is used: live
  tests are skipped on Windows, and so were xpublish-opendap's.
- `publish-to-pypi.yml` uses trusted publishing. Nothing has been released yet.
- **Do not copy** opendap's `docs/` or `notebooks/`: they are leftover IOOS
  skeleton boilerplate (`meaning_of_life()`), not a convention.

Codecov uploads fail with "Token required". This does not fail the job, but
the badge will not work until a `CODECOV_TOKEN` secret is added.

## Issue #6 has a design recommendation attached

A comment on #6 proposes the xpublish-edr pattern: register each output format
as its own entry point, with one module per format in a `formats/`
subpackage. This should be done **before** adding many more formats. `.das`,
`.dds` and `.ncml` should stay in core: they describe the dataset, and their
formatting has to match ERDDAP exactly.

## A source that fails is left out of the server-wide root (#56)

`ErddapPlugin.server_catalog` catches any exception per source (network, auth,
a deleted store, an unresolvable listed id, a cftime calendar `check_axes`
cannot handle), logs it as a warning naming the dataset, and serves the rest,
as ERDDAP does with datasets that fail to load. **Decision:** a source that
fails after loading once *drops out*; it does not keep its last good entry.
Serving a stale entry would hide that the store is unreachable, and the
failure is not cached, so the dataset returns on the next request after it
heals. The cost: one warning per request while it is down. The per-dataset
root (`/datasets/{id}/erddap`) is unchanged and answers with the error for its
own dataset only.
