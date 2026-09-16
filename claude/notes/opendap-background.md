# Background: how xpublish-opendap works, and early ERDDAP planning

Written 2026-09-15, while reading `xpublish-community/xpublish-opendap` (a
reference-only clone lives at `~/xpublish-opendap`; do not modify it). Moved
here 2026-09-16.

**Read the first half (how DAP2 and xpublish-opendap work) as reference.**
**The second half (the "reachable from ERDDAP" decision and its tiers) was
SUPERSEDED the same day.** EH has no ERDDAP server and does not want one, so
the work became this package. The reasoning is kept because it explains *why*
running a real ERDDAP with `EDDGridFromDap` was rejected. Current direction:
design-and-history.md.

## DAP2 in one screen

A dataset lives at a base URL; three suffixes give you everything:

- `.dds` — shape: names, types, dimension sizes (`text/plain`)
- `.das` — metadata: per-variable and global attributes (`text/plain`)
- `.dods` — XDR-encoded binary data with the DDS prepended (`application/octet-stream`)

The constraint expression is the **raw query string**, not key=value pairs:
`?air[0:1:10][0:1:24][0:1:52]` = variable `air`, `[start:stride:stop]` by
**integer index** on each dimension.

Type system: `Byte, Int16, UInt16, Int32, UInt32, Float32, Float64, String`,
plus `Array`, `Grid` (array + its coordinate vectors), `Structure`, `Sequence`.
No int64. No datetime.

The point of all this: netCDF-C has a DAP client compiled in, so MATLAB, R,
Julia, QGIS, Panoply, ncdump, ferret and `xr.open_dataset(url)` can all open a
DAP URL as if it were a local file. DAP is a compatibility shim for 25 years of
existing tooling — that is its entire value, and it is why it is worth serving
even though the protocol is dated.

## What the package actually does

Two files do the work.

### plugin.py — the HTTP surface

`OpenDapPlugin` implements one pluggy hook, `dataset_router`, returning a router
with prefix `/opendap` and three routes. Registered via the setuptools entry
point `xpublish.plugin` in pyproject.toml, so `pip install` is enough for
xpublish to discover it.

Two things that look odd and are deliberate:

- Routes are declared as `@router.get(".dds")`, so the path concatenates to
  `/datasets/air/opendap.dds`. A **suffix**, not a path segment, because that is
  what DAP requires. Do not "fix" this.
- `dap_constraint` reads `parse.unquote(request.url.components[3])` —
  `components[3]` is the `query` field of the urlsplit tuple. It grabs the raw
  query string and bypasses FastAPI's query parsing on purpose, because
  `air[0:1:10]` is not `key=value` and FastAPI would mangle it.

The translated `dap.Dataset` is cached in xpublish's cachey cache keyed by
dataset id. That caches the *object tree* (names, types, attrs, references to
the arrays), not the data — cheap, and correct because all three responses
rebuild the same tree.

### dap_xarray.py — the translation layer

Maps xarray's model onto DAP2's poorer one.

- dtype lookup table. `np.int64 -> dap.Float64` is marked "not a direct mapping"
  in the source: DAP2 has no 64-bit int, so int64 is silently widened and is
  lossy above 2^53.
- Dimensions get `xr.conventions.encode_cf_variable`, which turns `datetime64`
  into numerics plus `units: "hours since 1800-01-01"` — exactly what DAP
  clients expect. The following lines cast `>f4`-style big-endian dtypes back to
  little-endian so the lookup dict still matches; that guard exists because CF
  encoding can hand back big-endian.
- `dap_grid` passes `da.data` (the dask/Zarr-backed array), **not** `.values`.
  Nothing is computed at translation time. This is load-bearing — see below.

### The streaming mechanism (the part that matters for Icechunk)

`opendap_protocol` (MeteoSwiss; also mirrored in xpublish-community) is a
separate package and is where the real work happens. Its `dds`/`das`/`dods`
methods are **generators**: they parse the constraint expression, slice the
wrapped arrays, and yield XDR bytes. That is why the plugin wraps them in
`StreamingResponse`.

    GET /datasets/air/opendap.dods?air[0:1:10][0:1:24][0:1:52]
      -> cached dap.Dataset tree (lazy references)
      -> opendap_protocol parses the constraint
      -> slices the dask/Zarr/Icechunk-backed array
      -> yields XDR bytes as chunks land

Only the requested chunks are ever read from the store. A client asking for one
timestep of a 50 TB Icechunk store pulls exactly the chunks covering that
timestep. **This is the whole reason the pattern composes with Icechunk**, and
it is the property any ERDDAP work must preserve.

## Gaps in the translation (found by reading, not by testing)

Relevant if we extend or copy `dap_xarray.py`:

- Only dimension coordinates become DAP arrays. Non-dimension coords — 2-D
  curvilinear lat/lon, CRS variables, `bounds` — are dropped. Curvilinear model
  output loses its georeferencing.
- `dap_dimension` does `ds[dim]` for every entry in `ds.dims`; a dimension with
  no coordinate variable will raise `KeyError`.
- Dimensions get `encode_cf_variable`; data variables do not. A `datetime64` or
  `scale_factor`-encoded data variable falls through to the `dap.String`
  fallback.
- DAP2 only. No DAP4 (`.dmr`, `.dap`), which is where newer clients are heading.

## Earthmover

**Update: confirmed later.** Flux's DAP2 responses include a global attribute
`_xpublish_id`, so the DAP2 service *is* built on xpublish (see
cefi-flux-findings.md). The original caveat below is kept for the record.

Flux is a managed API layer over Arraylake/Icechunk serving
**EDR, WMS and DAP** from stateless autoscaling workers reading Icechunk out of
object storage. Their Tiles service is explicitly built on `xpublish-tiles`.

The Flux announcement does **not** name xpublish for the DAP endpoint, so
whether they run *this exact package* is unverified — do not repeat the claim as
fact. What is safe to say: the architecture is the xpublish-plugin pattern, and
xpublish-wms / xpublish-edr are the sibling plugins for the other two protocols.

- https://www.earthmover.io/blog/announcing-flux/
- https://www.earthmover.io/blog/dynamic-map-tile-rendering-icechunk-zarr-data-xpublish-tiles

## ERDDAP: the reframe

**ERDDAP griddap already is an OPeNDAP server.** `.das`, `.dds` and `.dods` are
supported griddap fileTypes. So this repo already implements the core of
griddap. ERDDAP adds four layers on top:

1. **Richer griddap queries.** `/erddap/griddap/{datasetID}.{fileType}?{query}`.
   Beyond integer `[start:stride:stop]`: coordinate-**value** subsetting with
   nearest matching `[(2020-01-01T00:00:00Z):1:(2020-02-01)]`, `[(35.5)]`;
   `last`, `last-3`, `(last)`, `(last-1)`; shorthands `[start:stop]`, `[start]`,
   `[]`. In xarray terms: `.sel(method="nearest")` vs `.isel()`. Resolve values
   to indices server-side, then hand off to the DAP path.
2. **~30 output formats.** `.nc .csv .csvp .json .jsonlCSV .nccsv .parquet .mat
   .itx .odvTxt .xhtml .ncoJson .ncml` plus images `.png .largePng
   .transparentPng .pdf .geotif .kml` and metadata `.fgdc .iso19115`. Each is
   "serialize the already-subset Dataset this way" — mechanical.
3. **tabledap.** `/erddap/tabledap/{id}.{ext}?var1,var2&time>=2020-01-01&latitude<50`.
   Row-oriented with filter predicates. A genuinely different data model, not a
   variation on griddap.
4. **Catalog and discovery.** `/erddap/search/index.json?searchFor=`,
   `/erddap/info/{id}/index.json`, `/erddap/griddap/index.json`,
   `/erddap/categorize/...`, `/erddap/version`, plus `.html` (Data Access Form)
   and `.graph` (Make A Graph). **This is the layer `erddapy` and
   `intake-erddap` actually drive.**

Plus a metadata contract: ACDD/CF globals (`title`, `summary`, `institution`,
`infoUrl`, `license`, `sourceUrl`, `cdm_data_type`, `Conventions`) and
per-variable `ioos_category`, `units`, `long_name`. Zarr/Icechunk stores
generally have none of `infoUrl`, `cdm_data_type` or `ioos_category`, so any
implementation needs a metadata-injection config — the moral equivalent of
ERDDAP's `datasets.xml`.

## State of the art: there is no xpublish-erddap

Checked the xpublish-community org (11 repos: xpublish, -wms, -edr, -opendap,
-zarr, -intake, -ogc-core, -intake-provider, opendap-protocol, .github,
community). No ERDDAP plugin exists. This would be new work.

## SUPERSEDED — DECISION (2026-09-15): reachable-from-ERDDAP, i.e. Tier 0

> **Superseded the same day.** EH has no ERDDAP server, and the goal became
> making erddapy/rerddap work with no ERDDAP at all, which is this package.
> The `EDDGridFromDap` spike below was **shelved, not done**. Everything down
> to "References" is historical.

EH settled the open question: **only reachable from ERDDAP.** We are not building
an ERDDAP-protocol server. Tiers 1-4 below are background//context only — do not
start work on them.

The driving requirement: users have existing **erddapy** (Python) and **rerddap**
(R) code against ERDDAP servers. That code must keep working essentially as-is,
while the data underneath is served from Icechunk.

Tier 0 satisfies this completely, and more cleanly than building a server would,
because the thing users talk to is a *genuine* ERDDAP. No protocol emulation, no
compatibility risk: every fileType, /info, /search, .graph and subscriptions all
work because it really is ERDDAP.

    Icechunk repo (object store)
      -> icechunk + xr.open_zarr
    xpublish + xpublish-opendap        (this repo, unmodified)
      -> DAP2 base URL: http://host:9000/datasets/{id}/opendap
    ERDDAP (Tomcat/Jetty), EDDGridFromDap in datasets.xml
      -> /erddap/griddap/{id}.nc?sst[(2024-01-01)][...]
    erddapy / rerddap / user scripts   UNCHANGED

**Strongest form:** if an ERDDAP already serves these datasets, swap one
dataset's backing from EDDGridFromNcFiles to EDDGridFromDap while keeping the
**same server URL and same datasetID**. Then user code changes by literally
nothing. On a new server the only edits are `server=` and `dataset_id=`; all
query logic survives.

**Why the DAP hop is needed at all:** ERDDAP's Zarr support is
EDDGridFromNcFiles/EDDTableFromNcFiles over *local files* with "zarr" in the
fileNameRegex. It cannot open a remote Icechunk repo, and Icechunk is not plain
Zarr anyway (transactional manifests).

### Work items

1. **Icechunk -> xpublish.** Open repo, hand Dataset to `xpublish.Rest` with
   `OpenDapPlugin()`. The four `dap_xarray.py` gaps listed below become
   production concerns here — especially `KeyError` on a dimension with no
   coordinate variable, and int64 silently widening to Float64. Probably needs a
   normalization pass on the Dataset before xpublish sees it.

2. **datasets.xml entry.** `sourceUrl` is the **base** URL — ERDDAP appends
   `.das`/`.dds`/`.dods` itself:

       <dataset type="EDDGridFromDap" datasetID="my_sst" active="true">
         <sourceUrl>http://xpublish-host:9000/datasets/my_sst/opendap</sourceUrl>
         <reloadEveryNMinutes>1440</reloadEveryNMinutes>
         <addAttributes>
           <att name="title">...</att>
           <att name="summary">...</att>
           <att name="institution">...</att>
           <att name="infoUrl">...</att>
           <att name="license">...</att>
           <att name="cdm_data_type">Grid</att>
           <att name="Conventions">CF-1.10, ACDD-1.3</att>
         </addAttributes>
         <dataVariable>
           <sourceName>sst</sourceName>
           <addAttributes>
             <att name="ioos_category">Temperature</att>
             <att name="units">degree_C</att>
             <att name="long_name">Sea Surface Temperature</att>
           </addAttributes>
         </dataVariable>
       </dataset>

   Real advantage of this path: ERDDAP's mandatory ACDD metadata is injected via
   `<addAttributes>`, so **the Icechunk store never has to carry
   ERDDAP-specific attributes**. On the be-ERDDAP path we would have had to
   build that entire config layer ourselves. Bootstrap the XML with ERDDAP's
   `GenerateDatasetsXml` against the DAP URL, then hand-edit.

3. **Freshness — the main operational gotcha. There are TWO stale caches.**

   - *ERDDAP* caches axis values at dataset load. Keep `reloadEveryNMinutes`
     high (1440) and have whatever commits to Icechunk hit
     `/erddap/setDatasetFlag.txt?datasetID=X&flagKey=Y` (or drop a file named
     `{datasetID}` into `bigParentDirectory/flag`) after each successful commit.
     This is ERDDAP's documented pattern for growing datasets.
   - *xpublish*, less obviously, and **this one is specific to our stack and
     easy to miss until data silently stops appearing.** Two problems:
     `xpublish.Rest({"id": ds})` pins one Icechunk snapshot for the process
     lifetime; and `plugin.py` caches the translated `dap.Dataset` in cachey at
     cost 99999 — that is an eviction priority, *not* a TTL, so it simply stays.
     An ERDDAP reload would therefore faithfully re-read a stale DDS. Needs a
     `get_dataset` provider hookimpl that opens a fresh Icechunk session, plus
     invalidation of that cachey entry.

4. **Ops.** Back to a JVM ERDDAP — not stateless, needs sizing and a
   `bigParentDirectory`. Check that ERDDAP's DAP request pattern lands on
   Icechunk chunk boundaries rather than straddling them.

### The one real unknown — do this spike first

**Does ERDDAP's Java DAP client accept xpublish-opendap's output?**
xpublish-opendap is DAP2 and runs in production at Gulf of Maine / IOOS, but
this has NOT been verified against ERDDAP specifically, and ERDDAP's client is
picky. (It also requires strictly rectilinear, sorted axes — curvilinear data
will not fit griddap regardless of transport.)

One-day spike, de-risks everything downstream: xpublish-opendap serving the
`air_temperature` tutorial dataset, a dockerized ERDDAP with a hand-written
EDDGridFromDap entry, and check the dataset loads and erddapy can pull from it.
If that works, the rest is assembly. Not yet started.

## Proposed tiers

**Tier 0 — CHOSEN, see DECISION above.** ERDDAP is itself a *client*. `EDDGridFromDap` in
`datasets.xml` points a real ERDDAP at any DAP URL. So: run xpublish-opendap in
front of Icechunk, register that URL in an existing ERDDAP, and get all of
griddap, every output format, the catalog and the graphs for free, in days. Cost
is running a JVM ERDDAP that caches and proxies, losing the stateless
autoscaling property.

(ERDDAP has gained direct Zarr reads, but only via `EDDGridFromNcFiles` /
`EDDTableFromNcFiles` — local files with "zarr" in the `fileNameRegex` — not
remote Icechunk. So Tier 0 still needs the DAP hop.)

**This question is now ANSWERED: reachable from, not be. See DECISION above.**

**Tier 1 — griddap MVP** (~80% of client value). An xpublish `dataset_router` at
`/erddap/griddap/{id}`: reuse `dap_xarray.py` wholesale for `.das`/`.dds`/`.dods`;
write the ERDDAP constraint parser -> `isel`/`sel` (the one genuinely new
algorithmic piece, and where `last-n` / `(value)` / stride interactions will
produce the bugs); six serializers, not thirty (`.nc .csv .csvp .json .jsonlCSV
.nccsv`); a per-dataset metadata-injection config.

**Tier 2 — discovery.** An `app_router`, not a dataset router:
`/erddap/info/{id}/index.json`, `/erddap/search/index.json`,
`/erddap/griddap/index.json`, `/erddap/version`. Acceptance test:
`erddapy.ERDDAP(server="http://localhost:9000/erddap")` works end to end.
erddapy and intake-erddap are already installed in EH's environment.

**Tier 3 — HTML/graphics.** `.html`, `.graph`, `.png`, `.pdf`. Large surface,
low protocol value; programmatic clients never touch it.

**Tier 4 — tabledap. Think hard before starting.** Structural mismatch:
xpublish's `deps.dataset` hands you an `xr.Dataset`; tabledap wants rows and
predicates. Two honest options — (a) declare out of scope, since for
n-dimensional Icechunk griddap is the right protocol and tabledap is a category
error; or (b) back it with a different store (Parquet/DuckDB, or Icechunk with
CF-DSG conventions) and use cf-xarray to recognize point/timeseries/trajectory
`cdm_data_type`s. Do not bolt it onto the array path.

## Suggested next step (historical)

Run this repo locally against an Icechunk store and open it from
`xr.open_dataset(url)` and from ncdump, watching which Zarr chunks get pulled.
The tiering above reads as obvious once that cycle has been observed; griddap is
that plus a query parser plus serializers.

## References

- ERDDAP griddap: https://coastwatch.pfeg.noaa.gov/erddap/griddap/documentation.html
- ERDDAP tabledap: https://coastwatch.pfeg.noaa.gov/erddap/tabledap/documentation.html
- ERDDAP datasets.xml: https://erddap.github.io/docs/server-admin/datasets
- xpublish-community: https://github.com/orgs/xpublish-community/repositories
- erddapy: https://ioos.github.io/erddapy/
