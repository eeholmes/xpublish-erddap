# Plan: parity with a real ERDDAP (issue #1)

Agreed with EH 2026-09-16. Branch `verify-erddap-parity`.

## What "client code" means here

The target users have ERDDAP code they already run. The examples EH gave:

- CoastWatch satellite course, R and Python tutorials 1 and 3
  (coastwatch.gitbook.io/satellite-course). They **build griddap URLs by hand**
  and download `.nc` with `urllib` / `httr::GET`, then read it with
  `xr.open_dataset(..., decode_cf=False)` + `netCDF4.num2date`, or `ncdf4`.
  Tutorial 3 uses date-only times (`2019-01-15`) and off-grid values
  (`19.2345832`); the real ERDDAP snaps both to the nearest point. R tutorial
  3 uses `rerddap::info` + **`rerddapXtracto::rxtractogon`** across the
  dateline on a 0–360 longitude axis. The dataset they use,
  `CRW_sst_v1_0_monthly` on oceanwatch.pifsc.noaa.gov, is now titled
  "ZZZ - DEPRECATED".
- erddapy docs `01a-griddap-output` (`etopo5_EDDGridCopy` on
  erddap.ioos.us): `griddap_initialize`, `latitude_step = 10`, a bounding box
  on 0–360 longitude, `to_xarray()`.
- IOOS code gallery "fetching data" is **tabledap** throughout. Deferred
  (#7): "later", not rejected.

## Deployment model (EH)

Each Arraylake store served by Flux gets `/erddap` beside its existing
`/opendap`, e.g. `.../NOAA-PMEL/cefi-nep-hindcast-daily/main/regrid/main/erddap`.

- **One ERDDAP root per store.** Catalog/org-level root is a later
  conversation with Earthmover (they have no STAC for the org yet).
- **Dataset IDs use the catalog's existing rule** (`sanitize_id` + a suffix
  per dimension split) for now.
- **OPeNDAP users (Ferret, EH's example) use `/opendap`,** not the ERDDAP path.
  So `.dods` on the ERDDAP path is low priority: it is kept out of the
  advertised fileTypes and answers 501 pointing at #2. Implement later by
  reusing xpublish-opendap's encoder.
- Response URLs are built from the request; behind Flux's proxy they must come
  out as the public host. Earthmover's side; check once deployed.

## Looser than ERDDAP, where clients allow it

A real ERDDAP's rules are not all client requirements:

- Required globals (`summary`, `license`, ...): ERDDAP-only. Default them.
- Shared dimensions: a server could cope, but `info/index.csv` lists
  dimensions once per dataset, so erddapy/rerddap build one bracket set for
  every variable. Keep splitting mixed stores into several dataset IDs.
- Strictly monotonic axes: **not** loosenable. Value constraints are nearest
  matches and are ambiguous on duplicate/unsorted axes (`strict_axes`).

The validator (#14) should check the client rules, not all of ERDDAP's.

## Steps

1. **Live parity tests.** Open a real ERDDAP dataset lazily through its own
   griddap OPeNDAP URL (`xr.open_dataset(".../griddap/<id>")` takes ~3 s for
   the 89 GB CRW set), serve it through xpublish-erddap, send the same
   requests to both, compare. Datasets: CRW monthly (tutorials),
   `etopo5_EDDGridCopy` (no time axis), plus one current CoastWatch set with
   descending latitude. Normalise only server URLs and timestamps; known
   mismatches are `xfail` with a reason. Marked `network`; run on a CI
   schedule, and captured responses are committed as golden files so normal
   CI does not need the network (EH agreed to both).
   Limit: the attributes arriving this way were already processed by ERDDAP,
   so this does not test raw Zarr attributes (step 4).
2. **Tutorial tests** on a CRW-shaped fixture (0–360 lon, monthly times at
   12:00, float64 SST), steps copied from each tutorial, Python and R
   (httr + ncdf4, rerddap::info + rxtractogon). Include the erddapy stride
   example, and a test with the plugin mounted under a store-like prefix.
3. **Fix what 1 and 2 find.**
4. Later: Docker ERDDAP in GitHub Actions for raw-Zarr golden files (the hub
   cannot run Docker: no socket, sudo blocked). Tabledap. `.dods`.

## Observed on the real ERDDAP

- Servers: oceanwatch.pifsc.noaa.gov runs ERDDAP 2.22, erddap.ioos.us 2.31.
  Our `/version` says 2.23.
- Reference datasets: `CRW_sst_v1_0_monthly` (tutorials; deprecated;
  ascending lat; times on the 1st at 12:00), `CRW_sst_v3_1_monthly` (current;
  **descending** lat; times on the **last** day of the month at 12:00),
  `etopo5_EDDGridCopy` on erddap.ioos.us (no time; float64 axes).
- A value range given against the axis order, e.g. latitude
  `[(19.3):1:(19.2)]` on an ascending axis, **is accepted for a
  data-variable request** (same rows as the forward order) but **fails for
  an axis-only request** (500 through the proxy). Same on the descending
  v3.1 axis with `[(19.2):1:(19.3)]`.
- **Nearest-match ties (#11): ERDDAP picks the larger coordinate value**,
  whichever way the axis runs, and for time too. Probed with exact float64
  midpoints on etopo5 (0.0417 -> 0.0833, -0.0417 -> 0.0), float32 ties on
  both CRW sets ((0.0) -> 0.025 ascending and descending), and a time
  midpoint (1985-01-17T00:00 -> 1985-02-01T12:00). We pick the first index.
- The info table's `variable` row **does** carry the variable's dimensions in
  `Value` ("time, latitude, longitude"), so the format can express
  per-variable dimensions; clients still build one bracket set per dataset.

## Store-level mount (2026-09-16)

`tests/server.py` mounts a second xpublish app at `STORE_PREFIX`
(`/v1/services/dap2/NOAA-PMEL/cefi-nep-hindcast-daily/main/regrid/main`), so
its ERDDAP root is `.../regrid/main/erddap`. Store id
`cefi-nep-hindcast-daily/regrid` -> datasetIDs
`cefi_nep_hindcast_daily_regrid` and `..._z_l` (catalog naming rule).
`tests/test_store_mount.py` (erddapy) and the end of `test_rerddap.R`
(rerddap) use it.

**Bug it found:** URLs we hand out (catalog, search, NcML location) dropped
the mount prefix. Starlette's `request.base_url` includes `root_path` behind
a `--root-path` proxy but *not* under `app.mount()`; `root_path` has the
prefix in both. `plugin.erddap_root()` now builds from it. How Flux actually
routes to a store app is Earthmover's; this covers both common ways.

## Info, NcML, DAS, small details (2026-09-16)

All 130 content comparisons now match; `KNOWN` is empty. Left on purpose:
`KNOWN_MEDIA` (ERDDAP 2.31 serves `.das` as text/csv) and the erddapy
`response="opendap"` xfail (#2). What ERDDAP does, as now implemented:

- **Numbers** are Java `toString`: shortest digits at the value's own
  precision, scientific below 1e-3 and from 1e7 (`4.734288E8`, `-1.0E34`);
  the DAS spells the exponent `e+8`. Used in info, NcML, DAS and CSV data.
- **Float32 axes are rounded to 7 significant digits** before ERDDAP derives
  `actual_range`, `geospatial_*`, `*most_*` and the spacing (Java
  `Math2.niceDouble(f, 7)`). Found on erdMH1chla8day (89.979164 ->
  89.97916); no effect on the 5-digit CRW grids. `catalog.nice_doubles`.
- **Info**: attribute Data Type from the value (`double`/`float`/`int`/...,
  Python int -> `int`); dimension Value `nValues=N, evenlySpaced=..,
  averageSpacing=..` with average = (last - first)/(n - 1), negative when
  descending; time spacing as `30 days 10h 27m 16s` / `1 day 0h 6m 4s`
  (zero parts and sub-day spacing are inferred, not observed); evenlySpaced
  tolerance is a guess (1e-5 relative for float32, 1e-9 otherwise). Variable
  Value is its dimension list. CSV writes a newline as the two characters `\n`.
- **NcML**: globals directly under `<netcdf>`, then dimensions, then
  variables; `type=` on non-String attributes; values space-separated;
  `'` escaped as `&#39;`. ERDDAP's `location` drops `/erddap`; we give the
  working URL (normalisation treats them as equal).
- Every attribute list is sorted ignoring case.
- `_NCProperties` **is** listed by ERDDAP in DAS/info/NcML but not written
  into `.nc` (an earlier note here said otherwise).
- DDS for a data request lists only its GRIDs; axes appear on their own
  only for the whole dataset or when requested by name.
- CSV writes missing values as `NaN`; JSON as null, with the time column
  typed `String`.

## Subset .nc metadata (2026-09-16)

All 9 `.nc` comparisons now match. In ERDDAP's `.nc` the coverage globals
(`geospatial_*_min/max`, the four `*most_*`, `time_coverage_*`) and each
axis's `actual_range` describe the subset **in the axis dtype** (float32 for
CRW); `geospatial_*_resolution` stays the full dataset's value; axes carry no
`_FillValue`; time is float64 epoch seconds, units spelled `...00Z`, no
`calendar`. `catalog.coverage_globals(subset=...)` does both cases.

`*most_*` are now derived for the full dataset too. Inferred, not proven:
etopo5 on erddap.ioos.us is a copy of IRI's worldbath.nc, which is unlikely
to carry them, yet its DAS lists them. `_NCProperties` (netCDF-4 library
stamp) is now dropped from globals like `_xpublish_id`.

## Fill values (2026-09-16)

`_FillValue`/`missing_value` now come from `.encoding` when not in `.attrs`
(`catalog._fill_attrs`), in the served dtype; packed data (scale/offset)
gets NaN, since we serve unpacked floats. Variable attributes are now
sorted like globals (ERDDAP sorts every attribute list, ignoring case). The
parity snapshot had been dropping `missing_value`; etopo5 was recaptured.

## Step 2: tutorial tests (2026-09-16)

`tests/tutorial_data.py` builds stand-ins with the real ids and **real axes**
(read from the parity snapshots; the CRW time axis is irregular, 35 months
not on the 1st) and formula values computed lazily per request, so values
are checked exactly. `tests/server.py` serves them next to `air`. Air's
metadata moved onto the dataset: plugin `metadata` applies to *every*
dataset.

- `tests/test_tutorials.py`: CoastWatch Python 1 and 3 (shapes 12x261x301 and
  12x252x424, as the tutorials print), erddapy `01a` (defaults are strings,
  step 10 gives 217x432, bbox coordinates match erddap.ioos.us exactly).
  `response="opendap"` is a strict xfail on #2.
- `tests/test_tutorials.R`: R 1 (GET + ncdf4) and R 3 (`info` +
  `rxtractogon` across the dateline). The tutorial's dataset is
  `goes-poes-monthly-ghrsst-RAN`; the stand-in is CRW. rxtracto fetches
  `csvp?time`, `?latitude`, `?longitude` itself, picks the enclosing cells,
  and requests exact values, so its box can extend one cell past the polygon.
- All pass. Nothing new found: our `.nc` time units spelled `+00:00` are
  read fine by `num2date` and ncdf4.

## Fixed on the branch (2026-09-16, PR #15)

Items 1, 2, 3, 8 and the #11 tie rule below. Float32 values and attributes
now print as written and are typed Float32; computed geospatial_* use the
written values and (max - min) / (n - 1), which reproduces ERDDAP's
0.049999999999999996. `actual_range` is now kept numeric (array in the axis
dtype) and each response formats it. Axis-only requests accept one
selector, refuse reversed ranges, and print columns side by side padded with
blanks. 138 pass, 33 xfail remain.

## Step 1 status (2026-09-16)

Built: `tests/parity/` (cases, capture, snapshot, compare) and
`tests/test_parity.py`; goldens committed (~770 KB); weekly workflow
`parity.yml` recaptures into a scratch dir, runs the tests against it, and
reports drift. Result: 75 pass, 57 strict xfail, grouped in `KNOWN`:

1. **float32 printed at float64 precision** (19.225000381469727) in csv/json,
   and float32 attributes typed/printed as Float64. Most visible to users.
2. **Globals sorted case-sensitively**; ERDDAP ignores case. (README quirk 3
   says "alphabetically" -- it is case-insensitive.)
3. **`_xpublish_id` leaks** into every globals listing.
4. `_FillValue`/`missing_value` missing from DAS/info/NcML/.nc (xarray keeps
   them in `.encoding`). Axes in our .nc get a NaN `_FillValue`.
5. info table: Data Type always "String"; dimension Value lacks
   `evenlySpaced`/`averageSpacing`; variable Value lacks dims; newlines not
   escaped as `\n`.
6. NcML: ERDDAP puts globals directly under `<netcdf>` with `type=`; we use
   an `NC_GLOBAL` group and no types; `location` should be the URL.
7. Subset `.nc`: ERDDAP rewrites actual_range, geospatial_*, *most_*,
   time_coverage_* for the subset; our time units say `+00:00`.
8. Axis variable with `[...]` selectors (`time[(last)]`) is rejected (400).
9. DDS for a data request should list only the GRIDs.
10. Ties (#11), CSV missing values should read `NaN`, JSON time
    columnType should be `String`, DAS number format (`4.734288e+8`).
11. Media type: ERDDAP 2.31 serves `.das` as text/csv (2.22: text/plain);
    not copying that.

- `curl` globs `[]`; use `curl -g`.
