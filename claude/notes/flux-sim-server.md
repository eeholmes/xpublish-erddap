# Flux-like test server (#17)

`deploy/server.py` simulates Earthmover Flux: one xpublish app with a dataset
provider plugin, stock xpublish-opendap, and xpublish-erddap, serving two public
Icechunk stores. It will run on AWS for the hackweek collaborators (Phase B,
teardown 2026-11-13).

## The two data pathways

| id | store | how it opens | notes |
|---|---|---|---|
| `cefi_nep_hindcast_daily` | Arraylake `NOAA-PMEL/cefi-nep-hindcast-daily`, `main`, group `regrid/main` | `arraylake.Client().get_repo()` | **Virtual** store; chunks are CEFI NetCDF files in NODD. Repo visibility is `AUTHENTICATED_PUBLIC`: anyone with an Arraylake login can read it, but the server needs a credential. Bucket `ems-noaa-pmel-...` is in **us-east-1**. |
| `gobai_o2_monthly` | Source Cooperative `fish-pace/gobai-o2/monthly` | `icechunk.s3_storage(bucket="us-west-2.opendata.source.coop", anonymous=True)` | Materialized Zarr v3. No credentials at all. **us-west-2**. Longitudes run 20.5–379.5 (from the source; monotonic, so it serves fine). |

The two stores are in different regions, so wherever the server runs, one of
them is read cross-region. Subsets are small, so it costs little either way,
but it shows up in latency.

## What the local run showed (2026-10-05, lean venv, Python 3.12)

`deploy/check_clients.py` and `deploy/check_rerddap.R` against
`http://127.0.0.1:9100`:

- erddapy `to_xarray` (nc) and `to_pandas` (csv) subsets of both stores work,
  and **match a direct read of the store**. rerddap `info()` and `griddap()`
  work for both. Subsets come back in 0.1–1 s on a warm server. The first
  request opens both stores (about 2.5 s).
- Every URL the server returns starts with the base URL. Behind Caddy this is
  the check that the public `https://` host came through
  (`uvicorn --proxy-headers`).
- The repo's tests pass in the lean venv: 220 passed, 4 skipped, 2 xfailed.
  Before, `tests/conftest.py` started the test server with whatever `python`
  was first on the PATH, not the venv's interpreter; it now uses
  `sys.executable`.

## Findings that became issues

- **#19, our bug:** ERDDAP treats `searchFor=all` as "every dataset". We
  return 404, and do the reverse for an empty `searchFor`. Checked against
  erddap.ioos.us.
- **#18, our gap:** under `SingleDatasetRest` the `/erddap` catalog is empty,
  with no error. Its comment records how Flux really routes (below).
- **#16:** no maximum response size. Needed before the public URL is shared.

## How Flux routes (probed 2026-10-05)

One app. The dataset is `{org}/{repo}/{ref}`, and the group is a path of any
depth: `.../main/opendap`, `.../main/regrid/opendap` and
`.../main/regrid/main/opendap` all answer, and parent groups give an empty
`Dataset { }`. This is xpublish 0.5's DataTree `{group_path:path}` routing.
`_xpublish_id` is `{org}/{repo}/{snapshot}/{group}`. `/plugins`, `/versions`
and `/docs` are 404 at a store path.

**EH believed Flux runs stock xpublish-opendap. The evidence says otherwise,
at least for the released version:** upstream has no group routing, and its
encoder (opendap-protocol 1.1.1) mis-reads DAP `[start:stride:stop]` as Python
`start:stop:step`. Stock gives 1 value for `lat[0:1:4]` and raises on
`time[0:1:0]`, which pydap requests whenever it opens a dataset; Flux gives the
correct 5. So the `/datasets/{id}/opendap` route on our server returns wrong
strided subsets. `check_clients.py` reports this as `KNOWN`. #2 has a comment.
Earthmover is the one to ask what they actually run.

## Environment gotchas

- xpublish-opendap 0.2.0 does not import on a fresh venv: opendap-protocol
  imports `pkg_resources`, which setuptools 81 removed. `deploy/requirements.txt`
  pins `setuptools<81`. The bloated hub env hid this.
- icechunk 2.x needs Python ≥ 3.12. On 3.11, pip quietly installs 1.x and
  `icechunk.http_storage` is missing.
- `pres` (GOBAI's pressure dimension) is on codespell's ignore list.
