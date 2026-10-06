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

- **#19, our bug (fixed, PR #26):** ERDDAP treats `searchFor=all` as "every
  dataset". We returned 404, and did the reverse for an empty `searchFor`.
  Checked against erddap.ioos.us.
- **#18, our gap:** under `SingleDatasetRest` the `/erddap` catalog is empty,
  with no error. Its comment records how Flux really routes (below).
- **#16 (done, PR #21):** no maximum response size.

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

## Phase B: on AWS (2026-10-05)

Stack `xpublish-erddap-demo` in EH's `greenfield` account (865526619870),
**us-east-2**, URL **https://18-119-42-78.sslip.io**, instance
`i-0e80a89b8eb8b2fcd` (t4g.medium). Teardown **2026-11-13**:
`deploy/aws/teardown.sh`, then revoke the Arraylake key.

Account facts a future session needs:

- An organization policy (SCP) allows EC2 **only in us-east-2**: us-east-1
  and us-west-2 are explicitly denied. SSM parameters in other regions are
  denied too.
- **JupyterHub sets `AWS_REGION=us-west-2`** for the hub's own account. Any
  script that honours it lands in a blocked region, and the error looks like
  a missing permission. The deploy scripts read `DEPLOY_REGION` instead.
- The account already has a **$100/month budget** (alerts at 85% and 100% of
  actual, 100% of forecast). It is shared with two LiteLLM t4g.small stacks
  (`litellm-smoke`, `agent-coders-gateway`), about $30/month between them.
  This server adds about $28/month (t4g.medium, Elastic IP, 20 GB gp3).
- The Arraylake key is a read-only API client in the **ocean-icechunks** org,
  stored as SSM SecureString `/xpublish-erddap-demo/arraylake-token`, as the
  other stacks store their secrets. A key from any org can read the CEFI repo
  (it is public to any logged-in account); verified with only the key.

Measured against the public URL:

- `check_clients.py`: 0 unexpected failures. Every returned URL is the public
  `https://` host, so Caddy's forwarded headers plus `uvicorn --proxy-headers`
  work. Subsets match a direct read of both stores.
- `check_rerddap.R`: all pass (0.2 to 0.8 s per call).
- Whole-variable `.nc` gives the 413 in 0.16 s, with no data read
  ("2910 MB is more than this server's 500 MB limit").
- HTTP redirects to HTTPS (308). The Let's Encrypt certificate for the
  sslip.io name was obtained on the first try.
- One 10-day CEFI subset (2.3 MB of csv): 2.3 s. Eight at once: about 12 s in
  total, so concurrent requests mostly queue on the 2-vCPU instance. Fine for
  a demo; a real deployment would want more workers.
- Server memory after the checks: 270 MB of 3.8 GB, no restarts.

## More datasets (#24, 2026-10-06)

EH listed six Flux URLs. All six open and serve, but **only the four
regridded ones are in** (PR #28): the two native-grid (`raw/main`) stores
split into 27 catalog rows under two titles, and EH said that was far too
busy. Keep the demo catalog small and readable over complete. With them went
a fix they needed: their `geolat`/`geolon` are 2-D coordinates, which the
plugin does not serve, so those datasets had no positions.

- The stores' own titles are model run names (`NEP10k_202507_physics_bgc`).
  `server.py` sets ERDDAP-style title/summary/infoUrl per store from the
  `CEFI` table, so a search for "ocean" finds them. License CC-BY-4.0 is
  from each Zenodo data DOI (checked via the Zenodo API).
- The NEP monthly store still splits in three (`_z_l`, `_zi` for depth).
- **rerddap vs a date axis not called `time`:** the decadal forecasts'
  `lead` holds dates. rerddap converts date strings only for `time` and
  fails with "argument is of length zero"; numeric seconds since 1970 work.
  erddapy is fine. Documented in `deploy/README.md`. Not checked against a
  real ERDDAP with such an axis.
- Stores open in a background thread at startup: first request 0.3 s
  instead of ~18 s. On AWS all six open in about 6 s; memory ~220 MB.

## Updating the running server without a shell session

`aws ssm send-command` runs the README's update steps non-interactively
(used twice on 2026-10-06; `env -u AWS_REGION aws --profile greenfield
--region us-east-2`):

```
ssm send-command --instance-ids i-0e80a89b8eb8b2fcd --document-name AWS-RunShellScript \
  --parameters 'commands=["set -e","cd /opt/xpublish-erddap","sudo -u xpe git fetch origin","sudo -u xpe git checkout main","sudo -u xpe git pull --ff-only","systemctl restart xpublish-erddap"]'
ssm get-command-invocation --command-id <id> --instance-id i-0e80a89b8eb8b2fcd
```

The package is installed editable, so a restart picks up new code. Then run
`deploy/check_clients.py https://18-119-42-78.sslip.io` from the hub.
