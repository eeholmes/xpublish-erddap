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
  beside its `/opendap`; one root per store for now. Details in
  `notes/erddap-parity-plan.md`.

## Repo state (2026-09-16)

- **#1 is done** (PR #15, merged): every captured real-ERDDAP response
  matches. #11 closed with it.
- The repo now uses **branches and PRs**; a task stays on its branch until
  the definition of done on its issue is met.
- CI: 10 jobs green, including a Linux R job (rerddap + tutorials). Local:
  220 passed, 4 skipped, 2 xfailed. The weekly `parity.yml` has not run yet.
- #13 is the hackweek proposal; #14 (the Zarr/Icechunk validator) is its
  second project. Collaborators are reviewing it.

## ⚠ Check the environment first

This JupyterHub **changes packages on every restart**, and there is no
Docker. Before trusting a local result, check erddapy (CI uses 3.3.1), that
`import xpublish_erddap` works, and `gh auth status`. Commands, fixes, and how
to run the R tests: `notes/dev-environment.md`.

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

- **Deployment blockers:** #3 (catalog cached forever), #8 (no auth).
- **#2 `.dods`:** reuse xpublish-opendap's encoder, later. A strict xfail in
  `test_tutorials.py` will flip when it works.
- **Raw Zarr attributes through a real ERDDAP** (Docker in Actions): not
  covered; needs its own issue first.
- Pinned dev environment, `CODECOV_TOKEN`, first PyPI release: all not started.
