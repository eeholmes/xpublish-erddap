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

- `[(19.3):1:(19.2)]` on an ascending latitude axis still returns data.
  Check what we do.
- `curl` globs `[]`; use `curl -g`.
