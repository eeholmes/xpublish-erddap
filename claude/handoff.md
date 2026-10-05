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

## Repo state (2026-10-05)

- **A public test server is live until 2026-11-13** (#17, PR #20):
  https://18-119-42-78.sslip.io/erddap, serving CEFI (Arraylake) and
  GOBAI-O2 (Source Cooperative S3) through `deploy/server.py`, on EH's AWS
  account. It runs `main`. Hackweek collaborators use it. **Tear it down on
  2026-11-13** with `deploy/aws/teardown.sh`, then revoke the Arraylake key
  (ocean-icechunks org). Account limits and results: `notes/flux-sim-server.md`.
- **#16 is done** (PR #21): `ErddapPlugin(max_response_mb=...)`, plus real
  ERDDAP's 2 GB `.nc` cap.
- **#1 is done** (PR #15): every captured real-ERDDAP response matches.
- The repo now uses **branches and PRs**; a task stays on its branch until
  the definition of done on its issue is met.
- CI: 10 jobs green, including a Linux R job (rerddap + tutorials): 231
  passed, 4 skipped, 2 xfailed on Linux/macOS; Windows skips the live-server
  tests (218 passed, 18 skipped).
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
- `tools/fluxlint.py` — rough readiness linter; a start for #14.

## Open threads (a record, not a task list)

- **Fitting into Flux:** #18 (per-group `/erddap`). Ask Earthmover how they
  run xpublish-opendap and would wire in an ERDDAP service before designing.
- **#19:** `searchFor=all` must list every dataset (real ERDDAP does).
- **Deployment blockers:** #3 (catalog cached forever), #8 (no auth).
- **#2 `.dods`:** reuse xpublish-opendap's encoder, later, but its released
  version mis-reads DAP strides (comment on #2). A strict xfail in
  `test_tutorials.py` will flip when it works.
- **Raw Zarr attributes through a real ERDDAP** (Docker in Actions): not
  covered; needs its own issue first.
- Pinned dev environment, `CODECOV_TOKEN`, first PyPI release: all not started.
