# Handoff — xpublish-erddap

## What this repo is

An xpublish plugin that serves the part of ERDDAP's `griddap` REST API that
users' **ERDDAP client code** relies on: erddapy, rerddap, rerddapXtracto, and
hand-built griddap URLs (the CoastWatch tutorials). When data moves from
ERDDAP servers to Zarr/Icechunk on Earthmover Arraylake, that code should
keep working with only the server URL changed. **Client compatibility, not an
ERDDAP replacement:** no UI, no images; tabledap is "later" (#7).

- Public at https://github.com/eeholmes/xpublish-erddap; the aim is to
  **donate it to xpublish-community**.
- **BSD-3-Clause on purpose** (matches the xpublish plugins; overrides the
  NOAA Apache-2.0 default). Do not flag or change it.
- `~/xpublish-opendap` is a **reference-only** clone. Do not modify it.
- **Deployment model (EH):** each Flux-served store gets an `/erddap` root
  beside its `/opendap`. Details in `notes/erddap-parity-plan.md`. Probing
  Flux (2026-10-05) showed it is one service per protocol, routed
  `.../services/{protocol}/{org}/{repo}/{ref}/{group path}/{protocol}`, so
  "beside" means a **per-group** ERDDAP root, which the `app_router` plugin
  cannot be yet (#18). Flux's DAP2 also behaves differently from the
  *released* xpublish-opendap, as EH's colleague suspected
  (`notes/flux-sim-server.md`).

## Repo state (2026-10-06)

- **A public test server is live until 2026-11-13** (#17 closed; PRs #20, #22):
  https://18-119-42-78.sslip.io/erddap, serving five regridded CEFI stores
  (Arraylake) and GOBAI-O2 (Source Cooperative S3) through `deploy/server.py`,
  on EH's AWS account: 8 ERDDAP datasets. It runs `main` (`7a62dd4`,
  redeployed 2026-10-06; how: `notes/flux-sim-server.md`). Hackweek
  collaborators use it. **Tear it down on
  2026-11-13** with `deploy/aws/teardown.sh`, then revoke the Arraylake key
  (ocean-icechunks org). Account limits and results: `notes/flux-sim-server.md`.
- **Collaborator test kit (2026-10-06), local only, deliberately not in
  git:** `collaborator-test/` on this hub, hidden by `.git/info/exclude`.
  EH shares it by Slack. `test_erddap_server.{py,R}` print PASS/FAIL per
  check (9/9 Python in a clean venv, 10/10 with icechunk's direct-read
  comparison; 7/7 R); `example_python.py` and `example_r.R` are plain
  user-style code (search, info, subsets, a plot). All point at the test
  server above, and were re-checked after #24 (all pass). Do not commit
  them unless EH asks.
- **Shipped 2026-10-06:** #19 search fix (PR #26: `searchFor=all`, refusing
  an empty query; search requests are now parity cases); #24 more datasets
  (PR #28). Closed #9, #16, #19, #24. Opened #27 (search columns differ
  from ERDDAP's). #29 plugin comparison (PR #31, awaiting EH's merge):
  report in `notes/plugin-comparison.md`, plan opened as #32–#37.
- **#16 is done** (PR #21): `ErddapPlugin(max_response_mb=...)`, plus real
  ERDDAP's 2 GB `.nc` cap.
- **#1 is done** (PR #15): every captured real-ERDDAP response matches.
- The repo uses **branches and PRs**; a task stays on its branch until
  the definition of done on its issue is met. Merged branches are deleted,
  on GitHub and on the hub (the repo does not auto-delete them).
- CI: 10 jobs green, including a Linux R job (rerddap + tutorials): 255
  passed, 10 skipped, 2 xfailed on Linux/macOS; Windows skips the live-server
  tests (240 passed, 26 skipped).
- #13 is the hackweek proposal; #14 (the Zarr/Icechunk validator) is its
  second project. Collaborators are reviewing it.

## ⚠ Check the environment first

This JupyterHub **changes packages on every restart**, and there is no
Docker. EH wants work done in a **lean venv**, not the notebook env:
`~/venvs/xpe` (Python 3.12, which icechunk 2.x needs). Check `gh auth status`.
**The hub sets `AWS_REGION=us-west-2`** for its own account; never let AWS
commands for EH's `greenfield` account inherit it. Commands, fixes, and how to
run the R tests: `notes/dev-environment.md`.

## Working principles

- **Real ERDDAP output is the contract, and it is tested.** Run
  `tests/test_parity.py` before changing `formats.py`, `catalog.py` or
  `plugin.py`. Some things look wrong but are ERDDAP's behaviour: Java
  numbers, float32 axes rounded to 7 digits, case-insensitive attribute order,
  ties going to the larger value.
- **When unsure what ERDDAP does, ask a real server,** then add the request to
  `tests/parity/cases.py` and recapture.
- **Test against lazily opened data**; never materialize a remote array.
- **Refuse bad axes instead of serving wrong answers** (`strict_axes`).
- **Check pass/skip counts in CI logs**, not just the colour.

## Notes

- `notes/flux-sim-server.md` — #17: the test server, both data pathways,
  how Flux really routes, AWS account limits, what was measured.
- `notes/erddap-parity-plan.md` — #1 end to end: the user code that counts,
  the deployment model, looser-than-ERDDAP rules (for #14), what real servers
  do and what is only inferred, how to recapture and add cases.
- `notes/dev-environment.md` — hub limits, setup checks, running R tests,
  probing real servers.
- `notes/client-compatibility.md` — client requirements, version drift,
  ERDDAP semantics we copy.
- `notes/design-and-history.md` — direction changes, structure, `strict_axes`.
- `notes/cefi-flux-findings.md` — CEFI via Flux: duplicate times, mixed dims.
- `notes/opendap-background.md` — DAP2 and xpublish-opendap (for #2).
- `notes/plugin-comparison.md` — #29: us against the community plugins and
  norms; a proposed plan.
- `tools/fluxlint.py` — rough readiness linter; a start for #14.

## Open threads (a record, not a task list)

- **Fitting into Flux:** #18 (per-group `/erddap`). Ask Earthmover how they
  run xpublish-opendap and would wire in an ERDDAP service before designing.
- **#27:** search (and maybe catalog) columns should be ERDDAP's 17.
- **#29:** compared with the other xpublish plugins; report and plan in
  `notes/plugin-comparison.md`. The plan became #32 (use `deps`), #33
  (xpublish 0.5 DataTree, bears on #18), #34 (split `app_router`), #35
  (tooling), #36 (error bodies), #37 (release and listing). The name clash
  with `xpublish-experiments/xpublish-erddap` is settled: Alex Kerney made it
  and is EH's collaborator.
- **More test data:** coastwatch.noaa.gov/erddap has ~1,045 griddap datasets
  and real ERDDAP error bodies (`notes/erddap-parity-plan.md`).
- **Deployment blockers:** #3 (catalog cached forever), #8 (no auth).
- **#2 `.dods`:** reuse xpublish-opendap's encoder, later, but its released
  version mis-reads DAP strides (comment on #2). A strict xfail in
  `test_tutorials.py` will flip when it works.
- **Raw Zarr attributes through a real ERDDAP** (Docker in Actions): not
  covered; needs its own issue first.
- Pinned dev environment, `CODECOV_TOKEN`, first PyPI release: all not started.
