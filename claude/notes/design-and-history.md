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
  purpose: some constraint-error wording (stride, selector count), and 400
  where ERDDAP gives 500 for an unknown variable. A **value** off an axis is a
  404 and index and `last` errors are 400s, all with ERDDAP's text (#57, #58;
  see below; the old note said ERDDAP gives 404 for an index, but CoastWatch
  gives 400, 2026-10-08). Parity compares the full
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
a deleted store, an unresolvable listed id; until #60, a cftime calendar), logs it as a warning naming the dataset, and serves the rest,
as ERDDAP does with datasets that fail to load. **Decision:** a source that
fails after loading once *drops out*; it does not keep its last good entry.
Serving a stale entry would hide that the store is unreachable, and the
failure is not cached, so the dataset returns on the next request after it
heals. The cost: one warning per request while it is down. The per-dataset
root (`/datasets/{id}/erddap`) is unchanged and answers with the error for its
own dataset only.

## A value off an axis is refused, not snapped (#57)

`constraints.check_in_range` is ported from ERDDAP's `EDDGrid.parseAxisBrackets`
(`validateGreaterThanThrowOrRepair`, then `validateLessThanThrowOrRepair`) and
`EDVGridAxis.initializeAverageSpacingAndCoarseMinMax`. A `(value)`, a
`(last-d)` result, start or stop, on a data variable or an axis-only request,
must lie within min − |avg spacing|/2 … max + |avg spacing|/2 (a one-value axis:
`max(|v|/100, 0.01)`), compared at 13 digits for time, 9 for a double axis, 5
otherwise (`Math2.lessThanAE`). Outside is a **404** (`NoMatchError`); inside but
off the axis still snaps to the nearest element. Only `repair=false` (the REST
path) throws; ERDDAP's HTML form and graph pages pass `repair=true` and clamp,
which we do not serve.

**Decision: the message is copied byte for byte, including a glitch.** The
"greater than the axis maximum" text ERDDAP sends begins with its own template
(`{0}="{1}" is greater than the axis maximum={2} (and even {3}).="Start" is
greater than...`) because `validateLessThanThrowOrRepair` passes the template as
an extra first argument. Both clients show the body to users and parity compares
it, so we match the real server (checked on erddap.ioos.us and two
coastwatch datasets, 2026-10-08, time and double axes). If ERDDAP fixes it, the
scheduled capture job will show the drift and the `greater` branch in
`check_in_range` should follow.

Two things that look fussy but are needed (found in review, 2026-10-08):

- **Values are ERDDAP's destination doubles, never `datetime64[ns]`.** Time is
  epoch seconds as a float (axis via `datetime64[us]`). The ns form wraps
  silently past 2262: `(2577-08-21T23:34:33)` wrapped to 1993-02-01 and was
  served with 200, and `(3000-01-01)` was called "less than the minimum".
  `_nearest_index` works on the same doubles.
- **A float32 axis's margin uses `nice_doubles`** (ERDDAP's 7-digit doubles),
  not the raw floats: erdMH1chla8day's live text is `(and even
  -90.00000333294744)`; raw floats give `-90.00000508655744`.

An unreadable value (`(abc)`, `(NaN)`, a bad date) is a **400**, `Start=NaN
(invalid format?) isn't allowed.`, ERDDAP's wording, checked before the range.

## Values and `last` are read with ERDDAP's own parsers (#58)

`xpublish_erddap/javaparse.py` ports `String2.parseDouble`/`parseInt` and
`Calendar2.parseISODateTime`/`parseN`/`isIsoDate`; `constraints._convert_last`
ports `EDDGrid.convertLast`, and `_resolve_token` follows `parseAxisBrackets`.
Things that look wrong but are ERDDAP's behaviour, checked on coastwatch's
jplMURSST41 (now a parity case, daily at 09Z):

- **A space in a time is a `+`.** A raw `+` in a URL is decoded to a space (we
  and ERDDAP both decode `+` as space), and `parseISODateTime` turns spaces back
  into `+`. So `+08:00`, `+08`, `+0800`, raw or `%2B`, all work. Do **not** fix
  this by changing `unquote_plus`: `searchFor` relies on `+` being a space, and
  a raw `last+0` is a 400 in ERDDAP too (`Unexpected character after "last"`).
- **Impossible dates roll over**: `2019-01-32` is Feb 1, `2019-13-01` is
  2020-01-01, `2019-02-30T25:61` is 2019-03-03T02:01. Fields are added to Jan 1
  in turn. Trailing junk ends the parse (`2019-01-01Tgarbage` is midnight).
- **Date or number?** On a time axis only text shaped like `yyyy-M...`
  (`isIsoDate`) is a date; `2019` and `20190102` are epoch seconds.
- **`last±n`** without parentheses is a strict integer (`last-1.5` is a 400
  with Java's `NumberFormatException` text, copied); with them any double, so
  `(last--86400)` is past the end (404).
- **An index is digits only and at most n-1.** `[-1]` is a 400, not the last
  element; `last-9000` past the start is reported as `Start="-108"`, the index
  it converted to.

`capture.py` now retries a 503 (CoastWatch under load); ERDDAP never answers a
request with 503, so a 503 is never a real answer. The jplMURSST41 case had
`metadata=False` until #78 fixed its Byte `mask`.

## Axes get ERDDAP's names; unsafe names are made safe (#59)

EH decided (2026-10-07) to rename recognised latitude, longitude **and time**
axes by default, with an option to turn it off or map names. Built in
`catalog.served_names`, applied in `build_catalog` with a lazy
`Dataset.rename`, so every response follows without format code knowing.
`ErddapPlugin(rename_axes=True | False | {source: served})`. Rules for hosts in
`docs/hosting.md` section 7. Decisions, with reasons:

- **DatasetIDs come from source names.** A split dataset's suffix is the
  source dimension (`s_z`, and `s_t` would stay `s_t`), so the option does not
  move datasets, and ids already handed out (the test server) stay put.
- **Recognition is ERDDAP's rule, tightened in two places.** Lat/lon: CF
  `standard_name`, CF degree units, or `EDV.probablyLat`/`probablyLon` (name
  plus unit compatibility, which GenerateDatasetsXml uses). So a unitless `lat`
  is renamed (ERDDAP would, and the fixtures `grid_dataset` and test_search's
  have such axes). Tightened: a bare `x`/`y`/`xax`/`yax` needs degree units
  (ERDDAP accepts them unitless; projected metres often are, see #60), and a
  non-matching `standard_name` (`grid_latitude`) or contradictory name and
  units (`lat` in `degrees_east`) means no rename. The issue said "units or
  standard_name" only; going with ERDDAP's name rule as well was deliberate,
  because `_axis_units` already *calls* a unitless `lat` `degrees_north`, and
  leaving its name alone would be inconsistent.
- **Time is datetime64 only.** The issue also listed "CF time units"; a
  numeric axis with `days since ...` that xarray did not decode is left alone,
  because we serve its numbers as they are and ERDDAP's `time` is always epoch
  seconds/ISO in UTC, which clients parse as such. Revisit if such stores
  appear (converting them would be the real fix).
- **Unsafe variable names are renamed, not refused** (issue item 16 asked to
  decide). Port of `String2.isVariableNameSafe` (ASCII letters only; ERDDAP
  allows ISO 8859-1, our constraint parser does not) and the last step of
  `EDD.suggestDestinationName`: `sst-anom` -> `sst_anom`, `1st` -> `a_1st`.
  Refusing would hide data the source plainly has; this is the name an ERDDAP
  admin would get from GenerateDatasetsXml. A clash with an existing name
  leaves the variable out (logged); an unservable axis refuses the dataset.
- **Target taken**: the axis keeps its source name, logged as a warning.

Checked: parity unchanged (real ERDDAP datasets already use these names), R
tests (rerddap, rerddapXtracto tutorials) with the new names, and an ad hoc
plotdap `add_griddap` on `air` now builds a plot (the committed plotdap test
is #67). The collaborator kit (`collaborator-test/`, local) still uses
`lat`/`lon` and must be updated when the test server is redeployed with this.

## Integer variables keep their type when xarray masks them (#78)

xarray's default decoding turns an integer variable with a `_FillValue` into
floats (NaN for the fill). ERDDAP serves it as stored, so
`catalog.served_dtype` takes the integer type from `.encoding["dtype"]` when
the variable is float, the stored type is integer and it is not packed.
`formats.dtype_of` uses it, so `.dds`, `.das`, `.ncml`, `info` and the json
column types all follow. Ported from ERDDAP's source and checked live:

- **Attributes in the variable's type** (`EDV` constructor): `_FillValue`,
  `missing_value`, `valid_min`, `valid_max`, `valid_range`. We also type
  `flag_values`/`flag_masks` (ERDDAP passes them through, but CF requires the
  variable's type, and from Zarr JSON they arrive as plain ints). A value
  that does not fit the type is left alone. Packed variables: see #64.
- **Fill cells are missing** (`Table.convertToStandardMissingValues`):
  `NaN` in csv, `null` in json, for any cell equal to `_FillValue` or
  `missing_value`, decoded or raw. Seen on oceanwatch's CRW_baa_max_7d_v1_0
  (Byte, fill 127 on land), now a parity case. `.nc` writes the integer type
  with the fill, as ERDDAP does.
- **Not copied:** ERDDAP standardises an integer column's missing value to
  the type's maximum and then treats *every* maximum as missing (`maxIsMV`),
  so a real 127 in a Byte with fill -128 is also `NaN`. That loses data, so
  we only blank the fill and missing values.
- **`_Unsigned` only in the DAS.** `OpendapHelper.dasToStringBuilder` adds
  `_Unsigned "false"` (`"true"` for ubyte) to every Byte variable without one,
  because DAP2 calls Byte unsigned. It is in no other response.

Found on the way, fixed because the jplMURSST41 metadata cases needed them:

- **The DAS is ISO-8859-1** (`text/plain;charset=ISO-8859-1`), a `°` one byte.
- **CSV text is ERDDAP's `String2.toSVString(s, 127)`** (`plugin.csv_cell`):
  JSON-escaped and quoted when it has a comma, quote, backslash, control
  character, non-ASCII character or edge space (`\u00b0`, `\n`).
- **json `columnUnits` is `null`** for a variable without units.
- **Capture repairs text** (`capture.repair_text`): over OPeNDAP a `°` arrives
  as U+FFFD and `history` carries ERDDAP's per-request lines; both are taken
  from ERDDAP's UTF-8 `info` JSON before the snapshot is written.

## Integer, unsigned and packed types follow ERDDAP (#64)

`.nc` is netCDF-3 (scipy), which has no unsigned or 64-bit types; it gave
500s. Ported from ERDDAP's source, checked on PacIOOS's `dhw_5km` (ERDDAP
2.29; coastwatch's `NOAA_DHW` is a proxy that redirects data requests
there, and the issue's `noaacrwdhwDaily` no longer exists):

| served | `.dds`/DAS | json, info, NcML | `.nc` |
| --- | --- | --- | --- |
| ubyte | `Byte`, attributes signed, `_Unsigned "true"` | `ubyte` | byte + `_Unsigned = "true"`, attributes signed |
| ushort, uint | `UInt16`, `UInt32` | `ushort`, `uint` | short, int + `_Unsigned`, attributes signed |
| long, ulong | `Float64`, attribute digits in full | `long`, `ulong` (NcML attributes double) | double, attributes double |

Sources: `OpendapHelper.getAtomicType`/`dasToStringBuilder`,
`NcHelper.getNc3DataType`/`newAttribute`, `NcmlFiles.writeNcmlAttributes`.

- **`_Unsigned = "true"` on signed storage is unsigned data** (netCDF-3's
  convention; dhw_5km's source). xarray leaves it in `.encoding` when it
  decodes and in `.attrs` when it does not; `served_dtype` reads both. The
  attribute is then dropped from every listing, as ERDDAP does, and added
  back only in the DAS (Bytes) and `.nc` (unsigned).
- **Packed variables** (`scale_factor`/`add_offset`): `_FillValue` and
  `valid_*` are unpacked, as `EDV` does. The fill is *not* NaN: coastwatch's
  jplMURSST41 gives `Float64 _FillValue -7.768000000000001` and
  `valid_min -7.767000000000003`, and we now print the same digits.
- **NcML text uses ERDDAP's entity table** (`XML.encodeAsXML`): `%` is
  `&#37;`, tab `&#9;`, other control characters dropped.
- **Capture:** netCDF-C's DAP client fails on dhw_5km's Byte variables
  ("NetCDF: DAP failure"), so `capture.block_reader` falls back to ERDDAP's
  own `.nc` for a data block; the snapshot keeps `_Unsigned` in encoding.

## Data is served as if ERDDAP's rules had been followed (#60)

**Principle (EH, 2026-10-08):** ERDDAP has many rules about how a dataset
must be formatted before it will serve it, so plenty of data never appears on
a real ERDDAP as stored. We do not impose those rules; we serve what an ERDDAP
admin would have converted the data to. Refuse only when there is no honest
conversion (non-monotonic axes, a date with no Gregorian equivalent). Stated in the README's
"Notes for anyone extending this". The audit's issue had assumed refusing
cftime was the cheap option; EH chose serving.

**A format or calendar may change, a time may not (EH, 2026-10-08).** The
first version of #60 moved days to make daily `360_day` and `all_leap` fit
(xarray's `align_on="year"`, then a year fraction) and kept Julian labels;
EH rejected both because they change times. `test_no_served_time_differs_from_its_source`
enforces the rule for 9 calendars; it was checked to fail when Julian keeps
labels or when any time moves by one second.

**cftime axes** (`xpublish_erddap/timeaxes.py`). ERDDAP never reads
`calendar`: `EDVTimeStampGridAxis` converts with
`Calendar2.getTimeBaseAndFactor`, so a noleap axis on a real ERDDAP drifts
(`days since 1993-01-01`: 7 days early by 2024, 360_day 162 days early) and
the untouched `calendar` attribute makes xarray clients shift it again. No
public ERDDAP of ~25 searched has a noleap/360_day dataset. We do not copy
it. **Model calendars** (`noleap`, `365_day`, `360_day`, `all_leap`,
`366_day`) have labels, not moments, so each **label is kept**. Every noleap
date is a Gregorian date; monthly `360_day` (day 16) is too. A label that is
not a Gregorian date (Feb 29/30 in daily `360_day`, Feb 29 2001 in
`all_leap`) **refuses the dataset**, logging the first such date: ERDDAP time
is one number of Gregorian seconds, so no value means "2001-02-29".
**Real calendars** (`julian`, `standard`/`gregorian` before 1582,
`proleptic_gregorian` out of datetime64[ns] range) are converted **by moment**
with cftime's `change_calendar`: Julian 1900-01-01 is served as 1900-01-13;
the standard calendar's 1582-10-04 -> 1582-10-15 jump is one day. A year
before 1 is refused. The served axis is `datetime64[us]` (no 2262 limit),
`calendar` dropped, and the source calendar and rule appended to the axis
`comment`. Conversion happens in `build_catalog`, on the 1-D axis only; data
stays lazy.

**timedelta axes** (`lead_time`, `step`): served as numbers in their source
units (`encoding["units"]`, e.g. `hours`) and source integer type, as an admin
would set them up. This fixed `v[(3)]` returning lead 0 and `.nc` failing.

**Projected x/y** in metres are not lat/lon: `coverage_globals` and
`_axis_units` use `recognised_axis` (#59's ERDDAP-ported test, under which a
bare `x`/`y` needs degree units) rather than the name list. A dimension with
no coordinate named `y` gets units `"1"`.

**Derived globals follow `EDDGrid`, not the issue.** The issue asked that a
supplied `geospatial_lat_min` survive. ERDDAP's `EDDGrid` constructor instead
*removes* `geospatial_lat/lon_*`, the four `*most_*` bounds and
`time_coverage_*`, whatever their source (store or `addAttributes`), and
derives them from the axes named `latitude`, `longitude`, `time`; a grid with
none of those has none. We now do the same, so a polar grid has no lat bounds
and is not found by a `minLat` search (as on ERDDAP). The case that motivated
the issue's version, wrong bounds from metre axes, is gone with the x/y fix.
EH confirmed following ERDDAP here (2026-10-08).
