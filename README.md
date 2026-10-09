# xpublish-erddap

[![tests](https://github.com/eeholmes/xpublish-erddap/actions/workflows/tests.yml/badge.svg)](https://github.com/eeholmes/xpublish-erddap/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](https://github.com/eeholmes/xpublish-erddap/blob/main/LICENSE.txt)

An ERDDAP-compatible `griddap` router for [Xpublish](https://github.com/xpublish-community/xpublish),
so that existing **[erddapy](https://ioos.github.io/erddapy/)** and
**[rerddap](https://docs.ropensci.org/rerddap/)** code keeps working when the data
moves to Zarr/Icechunk.

The goal is *client compatibility*, not an ERDDAP replacement. There is no Data
Access Form, no Make-A-Graph, and no tabledap yet — just the REST surface those two
client libraries actually call, so users' scripts run unchanged against an
Xpublish server.

```
Icechunk / Zarr / any xarray Dataset
  -> xpublish + xpublish-erddap
  -> erddapy / rerddap, unmodified
```


## Motivation

A lot of earth data is moving to cloud-native formats such as
Zarr — and increasingly to [Icechunk](https://icechunk.io) stores on platforms like
Earthmover's ArrayLake. That migration is good for analysing and accessing data at scale, but it breaks people's existing code that accessed the data before migration.

Many of our users reach our data through the ERDDAP ecosystem: **[erddapy](https://ioos.github.io/erddapy/)**
in Python, **[rerddap](https://docs.ropensci.org/rerddap/)** in R, etc, and a large body
of scripts, notebooks, teaching material and operational workflows built on top of
them. Those tools speak ERDDAP's REST API — `griddap` URLs with ERDDAP's own
subsetting syntax, plus its `info` and `search` endpoints. They cannot talk to a
Zarr store or an Icechunk repository.

**The goal of this plugin:** put an ERDDAP-compatible API in front of generic xarray-readable data,
so that a Zarr or Icechunk dataset can be reached with the ERDDAP tooling people
already use. With this plugin, migrating a dataset off an ERDDAP server can become
invisible to the people using it — their existing `erddapy` and `rerddap` (etc, etc) code keeps
working, unchanged. An example of a similar concept for OPeNDAP access to Icechunks on ArrayLake via [xpublish-opendap](https://github.com/xpublish-community/xpublish-opendap) already works [here](https://app.earthmover.io/NOAA-PMEL/cefi-nep-hindcast-daily/data-access/main/regrid/main?method=dap2). This plugin extends this concept to allow access to Zarr/Icechunk via the ERDDAP API.

## Status

Working end to end against both clients, on synthetic data and on real NOAA CEFI
model output served from Icechunk via Earthmover Flux. Not production software:
[no authentication](#access-control), no tabledap yet, a partial file-type list, and the catalog is built eagerly
at first request.

## Access control

This plugin does no authentication or authorization of its own callers.
Every dataset it is given is public to anyone who can reach the server.
If you serve a private Arraylake or Icechunk repo with it, that data becomes
public: the server opens the store with its own credentials and answers anyone.

Put access control in the hosting layer instead: a reverse proxy, the
platform's own auth (such as Earthmover Flux's), or middleware or dependencies
that you add to the FastAPI/xpublish app. The plugin can add routes but not
middleware. The same goes for stopping a caller from asking for too much; the
plugin's `max_response_mb` cap is a guard, not a quota.

If a host does add HTTP authentication, the clients can send it. `erddapy` has
an `auth` attribute (a `(user, password)` tuple for HTTP Basic, used by
`to_xarray`) and a `requests_kwargs` argument passed on to `requests`;
`rerddap` passes named arguments on to `crul`. This is read from their source and
docs, not tested against this server.

How the server reaches a private store (the other direction) is in
[docs/hosting.md](docs/hosting.md#reaching-a-private-store).

## Installation

```shell
python -m pip install xpublish-erddap
```

This installs the plugin with its dependencies (`xpublish`, `fastapi`,
`xarray`, `pandas`, `numpy`, `scipy`); it needs Python 3.11 or newer.
Xpublish finds the plugin through its `xpublish.plugin` entry point, or you
can pass `ErddapPlugin()` explicitly as below. To read Zarr or Icechunk
stores, also install what xarray needs for them (`zarr`, `icechunk`). Until
the first release is on PyPI, install from GitHub:
`python -m pip install git+https://github.com/eeholmes/xpublish-erddap.git`.

## Usage

```python
import xarray as xr, xpublish
from xpublish_erddap import ErddapPlugin

ds = xr.open_zarr("...")  # or icechunk, or anything xarray opens

# ERDDAP requires these; most Zarr stores do not carry them.
# This is the equivalent of ERDDAP's datasets.xml <addAttributes>.
metadata = {
    "title": "My Dataset",
    "summary": "...",
    "institution": "...",
    "infoUrl": "https://example.org",
    "license": "[standard]",
}
rest = xpublish.Rest({"my_dataset": ds}, plugins={"erddap": ErddapPlugin(metadata=metadata)})
rest.serve(port=9000)
```

Then, unchanged client code:

```python
from erddapy import ERDDAP

e = ERDDAP(server="http://localhost:9000/erddap", protocol="griddap", response="nc")
e.dataset_id = "my_dataset"
e.griddap_initialize()
e.constraints.update({"time>=": "2024-07-01", "time<=": "2024-07-05"})
ds = e.to_xarray()
```

```r
library(rerddap)
i <- info("my_dataset", url = "http://localhost:9000/erddap/")
d <- griddap("my_dataset", url = "http://localhost:9000/erddap/",
             time = c("2024-07-01", "2024-07-05"), fields = "tos")
```

### One ERDDAP root per dataset, or per group

Besides the server-wide `/erddap`, every dataset gets its own ERDDAP root
listing only that dataset: `http://localhost:9000/datasets/my_dataset/erddap`
under `xpublish.Rest`. A host that puts a group path in its dataset routes, as
Earthmover Flux does beside each group's `/opendap`, gets one root per group,
because the plugin reads its data only through the dependencies xpublish passes
it. Under `xpublish.SingleDatasetRest` the dataset's root is `/erddap` itself.
DatasetIDs follow the same rule everywhere: the dataset's id, then the group
path (`my_dataset` + `regrid/main` gives `my_dataset_regrid_main`). Where the URL
names no dataset (`SingleDatasetRest`), the id is `dataset`; pass
`ErddapPlugin(name_dataset=lambda params, group: "my_dataset")` to change it.

### Keeping up with data that changes

The plugin caches each dataset's catalog (axes, attributes) and rebuilds it when
the dataset's `_xpublish_id` attribute changes, the key xpublish and its other
plugins use. Earthmover Flux puts the Icechunk snapshot in that id, so new
commits appear on the next request. Plain `xpublish.Rest` uses the dataset id,
which never changes: for a store that changes in place, put a version in
`_xpublish_id` or set `ErddapPlugin(catalog_max_age_s=600)` to rebuild at least
every 10 minutes. Details: [docs/hosting.md](https://github.com/eeholmes/xpublish-erddap/blob/main/docs/hosting.md).

**Running the plugin in a host such as Earthmover Flux?** See
[docs/hosting.md](https://github.com/eeholmes/xpublish-erddap/blob/main/docs/hosting.md) for the choices it makes about routing,
naming and URLs, and what to change if yours differs.

### Limiting response size

Responses other than `.dods` are built in memory, so a request for a whole
variable can be gigabytes. (`.dods` streams, reading a block of the store at a
time, but is limited the same way.) By default (`max_response_mb=500`) the plugin refuses any data
request (`.nc`, `.csv`, `.json`, ...) whose values would exceed 500 MB. It
answers the way a real ERDDAP server does, with a 413 "Your query produced too
much data" error, and it decides from the query before reading any data. The
estimate is the size of the values themselves; text formats come out several
times larger. Metadata requests (`.das`, `.dds`, `.ncml`, info, search) are never
limited.

Set another number to move the limit, for example
`ErddapPlugin(max_response_mb=100)` on a small server. ERDDAP itself has no
fixed default: it refuses what would not fit in 75% of its Java heap
(`Math2.ensureMemoryAvailable`). `ErddapPlugin(max_response_mb=None)` means no
limit of your own; one limit still applies, copied from real ERDDAP servers,
which refuse any `.nc` response over 2 GB (`EDDGrid.saveAsNc`) and any `.dods`
array of 2^31 - 1 values or more (DAP2 sends its length as a 32-bit int), so
client code sees the same error either way. Use `None` only where a request for a whole
variable is safe.

## What is implemented

| Endpoint | Purpose |
| --- | --- |
| `/erddap/griddap/{id}.{ext}?{query}` | data; `ext` in `nc, ncml, csv, csvp, csv0, json, das, dds, dods`. With `.dds`, `.das` and `.dods` the bare griddap URL is an OPeNDAP URL, so `xr.open_dataset("<server>/erddap/griddap/<id>")` (netCDF-C or pydap) and erddapy's `response="opendap"` work, as on ERDDAP ([#2](https://github.com/eeholmes/xpublish-erddap/issues/2)) |
| `/erddap/griddap/index.{csv,json}`, `/erddap/info/index.{csv,json}` | dataset catalog, in ERDDAP's 15 columns (as on coastwatch.noaa.gov); links to services this plugin does not offer are empty |
| `/erddap/tabledap/index.{csv,json}` | empty catalog (rerddap needs it to classify a dataset) |
| `/erddap/info/{id}/index.{csv,json}` | variable and attribute table |
| `/erddap/info/{id}/index.html` | a minimal page (title and links), not ERDDAP's: rerddapXtracto's `safe_info()` and rerddap's `browse()` request this URL and need it to exist ([#62](https://github.com/eeholmes/xpublish-erddap/issues/62)) |
| `/erddap/search/index.{csv,json}`, `/erddap/search/advanced.{csv,json}` | search, as ERDDAP's default ("original") engine: every word must appear, `"quoted phrases"`, `-word` to exclude, ranked by where the words appear; `searchFor=all` lists every dataset. Advanced search also filters by `protocol`, the category attributes (`institution`, `keywords`, `ioos_category`, `long_name`, `standard_name`, `variableName`, `cdm_data_type`) and lon/lat/time bounds; `page` and `itemsPerPage` work |
| `/erddap/categorize/index.{csv,json}`, `/erddap/categorize/{attribute}/index.{csv,json}`, `/erddap/categorize/{attribute}/{value}/index.{csv,json}` | browse by category (erddapy's `get_categorize_url()`), as ERDDAP's default `categoryAttributes`: `cdm_data_type`, `institution`, `ioos_category`, `keywords`, `long_name`, `standard_name`, `variableName`. The first level lists the attributes, the second their values (lower case, file-name safe, `_null` where a dataset has none), the third the datasets with that value, in the dataset table, by title. A value in the wrong case redirects to the lower-case one; an unknown attribute or value is ERDDAP's 404 |
| `/erddap/convert/*` | refused at once with ERDDAP's 404 for a server whose converters are switched off (`The "convert" system has been disabled on this ERDDAP.`); interpolate is a future extension ([#98](https://github.com/eeholmes/xpublish-erddap/issues/98)). rerddapXtracto's `rxtracto(interp=...)` still retries any non-200 answer 11 times (about 33 s) before giving up |
| `/erddap/version` | version banner |

Every route answers `HEAD` as well as `GET`, as ERDDAP does (erddapy's `check_url_response()` and rerddapXtracto's `safe_info()` use it); a data request is validated but its file is not built.

Errors come back as ERDDAP's plain-text body (`Error { code=404; message="Not Found: ..."; }`), which is what erddapy and rerddap show their users.

Constraint syntax: coordinate values `[(2024-07-01):1:(2024-07-05)]`, integer
indices `[0:1:10]`, strides, `last` / `last-N` / `(last)` / `(last-N)`, and the
`[start:stop]` / `[start]` / `[]` shorthands.

## Notes for anyone extending this

ERDDAP clients are coupled to ERDDAP's exact *formatting*, not just its URL
scheme. Four cases found the hard way, all covered by tests:

1. `erddapy` parses the DDS with `data.split("GRID")`, so `GRID`/`ARRAY`/`MAPS`
   must be uppercase — DAP2's own spelling (`Grid {`) yields zero variables.
2. `rerddap` asserts `content-type == "application/json;charset=UTF-8"` exactly.
3. `rerddap`'s `info()` reads `time_coverage_end`/`_start` *positionally*, which
   only works because ERDDAP emits `NC_GLOBAL` attributes alphabetically
   (ignoring case, as checked against real servers).
4. `actual_range` must be rendered `"min, max"`, not Python's `"[min, max]"`,
   or `rerddap` silently coerces it to `NA`.

Two further constraints are structural rather than cosmetic:

**One hypercube per dataset.** An ERDDAP dataset has a single set of axes that
every data variable shares, so a source whose variables have differing
dimensions maps to *several* ERDDAP datasets. `catalog.build_catalog` does that
split, suffixing the extra datasets with their distinguishing dimension. Tested
against a real CEFI group of 92 variables, which splits into three.

**Axes must be strictly monotonic.** ERDDAP refuses a dataset whose axes are
not, and so does this package (`strict_axes=True`, the default), logging which
axis broke and where. Serving such data anyway is worse than refusing it:
coordinate-value requests still look correct, because nearest-match lands on the
first occurrence, while index ranges spanning the break silently return a series
that jumps backwards in time. Pass `strict_axes=False` to override.

**Axes have ERDDAP's names.** ERDDAP calls the geographic axes `latitude` and
`longitude` and the time axis `time`, and client code is written against those
names. A store with `lat`/`lon`/`t` axes is served with ERDDAP's names
(`rename_axes=True`, the default); `rename_axes=False` keeps the source names,
and a dict gives your own mapping. Variable names ERDDAP cannot serve
(`sst-anom`) are served as ERDDAP would name them (`sst_anom`). The rules are in
[`docs/hosting.md`](https://github.com/eeholmes/xpublish-erddap/blob/main/docs/hosting.md#7-axis-and-variable-names).

**Data is served as if ERDDAP's rules had been followed.** An ERDDAP server
accepts a dataset only once it is formatted the way ERDDAP requires, so much
data never appears on one as it is stored. This package does not impose those
rules on a store. Where a store has something ERDDAP would not accept, it
serves what an ERDDAP administrator would have converted it to. A conversion
may change a format or a calendar, never a value: where that is impossible,
the dataset is refused with a log line (as with non-monotonic axes, above).
For example, a time axis in another calendar is served as ERDDAP's
`seconds since 1970-01-01T00:00:00Z`, with the source calendar recorded in the
axis's `comment`. A model calendar's dates are kept as they are (`noleap`
2010-06-15 is served as 2010-06-15); a real calendar's moments are kept
(`julian` 1900-01-01 is served as 1900-01-13, the same day); an axis with a
date that does not exist in the Gregorian calendar (Feb 30 in daily
`360_day`) is refused. Real ERDDAP ignores the `calendar` attribute and serves
such dates days or months off. A forecast lead time (`lead_time`, `step`) is
served as numbers in its source units. The reasoning is in
[#60](https://github.com/eeholmes/xpublish-erddap/issues/60).

**tabledap is in scope, as a future extension.** Much ERDDAP client code is
observational (gliders, buoys, cruises) and calls `protocol="tabledap"`, so
serving it fits the goal of keeping that code working. It is a different data
model, though: rows with filter predicates (`&time>=...&latitude<50`) rather
than n-dimensional arrays, so it will need its own source type (Parquet,
DuckDB, or CF-DSG Icechunk) rather than the griddap path. Until then
`tabledap/index` answers as a server with no tabledap datasets. Tracked in
[#99](https://github.com/eeholmes/xpublish-erddap/issues/99); decided in
[#7](https://github.com/eeholmes/xpublish-erddap/issues/7).

## Demos

`demo/serve_air.py` serves xarray's tutorial dataset; `demo/serve_cefi.py`
serves real NOAA CEFI output read from Earthmover Flux. `demo/demo_rerddap.R`
and `demo/demo_cefi.R` exercise the R client.

## Reuse and citation

This work is released under the [BSD 3-Clause License](https://github.com/eeholmes/xpublish-erddap/blob/main/LICENSE.txt), matching
the other Xpublish plugins (`xpublish-opendap`, `xpublish-edr`, `xpublish-wms`),
so that it can be contributed to
[xpublish-community](https://github.com/xpublish-community). You are free to use,
copy, modify, and redistribute it, including commercially. If you use it in
published work, in a presentation, or in another repository, please give
attribution:

> Holmes, E.E. (2026). *xpublish-erddap: ERDDAP-compatible griddap router for Xpublish*.
> https://github.com/eeholmes/xpublish-erddap

## Development

```shell
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pre-commit install
pytest tests            # includes live-server erddapy and tutorial tests
Rscript tests/test_rerddap.R   # after starting `python tests/server.py`
Rscript tests/test_tutorials.R # same server; needs rerddapXtracto, httr, ncdf4
```

`nox` runs the suite against the same Python versions as CI. CI also runs the
erddapy-using tests with erddapy pinned to 3.1.0 (the `erddapy-3-1` job; the
matrix gets the newest erddapy) and the R tests with the newest rerddap.

**Client versions tested** (CI, 2026-10-09): erddapy 3.1.0 (pinned) and 3.3.1
(newest on conda-forge); rerddap 1.3.0 and rerddapXtracto 1.2.5 (newest on
CRAN). The newest versions move with each release; the CI logs say which ran.

`tests/test_tutorials.py` and `tests/test_tutorials.R` run the users' own
tutorial steps (CoastWatch satellite course, erddapy docs) against stand-in
datasets; `tests/test_store_mount.py` serves the plugin below a per-store
path, as Earthmover Flux would.

`tests/test_parity.py` compares our responses with captures from real ERDDAP
servers, committed under `tests/parity/golden/`; known differences are listed
in the test as expected failures. `python tests/parity/capture.py` refreshes
the captures (it needs the network), and the `Parity with live ERDDAP`
workflow does the same weekly without committing.
