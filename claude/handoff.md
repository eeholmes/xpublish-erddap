# Handoff — xpublish-erddap

## What this repo is

An xpublish plugin that serves the part of ERDDAP's `griddap` REST API that
users' **ERDDAP client code** relies on: erddapy, rerddap, rerddapXtracto, and
hand-built griddap URLs downloaded with urllib/httr (the CoastWatch tutorials).
The goal: when data moves from ERDDAP servers to Zarr/Icechunk on Earthmover
Arraylake, that code keeps working with only the server URL changed. It is
**for client compatibility, not an ERDDAP replacement**: no UI, no image
output. Tabledap is deferred ("later"), not rejected (#7).

- Public at https://github.com/eeholmes/xpublish-erddap. The aim is to
  **donate it to xpublish-community**.
- **The license is BSD-3-Clause on purpose.** It matches the xpublish plugin
  family and **overrides the NOAA Apache-2.0 default** in the global
  instructions. Do not flag it or change it.
- `~/xpublish-opendap` is a **reference-only** clone of the sibling plugin.
  Do not modify it.

**Deployment model (EH, 2026-09-16):** each Arraylake store served by Flux
gets an `/erddap` root beside its existing `/opendap`, e.g.
`.../NOAA-PMEL/cefi-nep-hindcast-daily/main/regrid/main/erddap`. One ERDDAP
root per store for now; dataset IDs follow the catalog's naming rule. An
org-wide catalog, and whether Flux adds the plugin, are conversations with
Earthmover still to come (EH: "we are their client"). OPeNDAP users, e.g.
Ferret, keep using `/opendap`, so `.dods` on the ERDDAP path is low
priority.

## Repo state (2026-09-16)

- **PR #15 merged: #1 is done.** Every captured real-ERDDAP response matches.
  See `notes/erddap-parity-plan.md`.
- **This repo now uses branches and PRs** (PR #15 was the first). The old
  branch `verify-erddap-parity` still exists locally and on GitHub; it is
  merged.
- CI: 10 jobs green (3 OSes × Python 3.12–3.14, plus a Linux R job that runs
  `test_rerddap.R` and `test_tutorials.R`). Local: 220 passed, 4 skipped,
  2 xfailed. The Windows jobs skip the live-server tests.
- New weekly workflow `parity.yml` recaptures from the live ERDDAP servers.
  **It has not run yet.**
- #13 is the hackweek proposal (collaborators reviewing); **#14 is its second
  project, the Zarr/Icechunk validator.**
- #11 (tie-breaking) was answered and fixed in #15 but is still open.
  Closing it is EH's call.

## ⚠ Check the environment before trusting any local result

This is a **JupyterHub, and packages change whenever the server restarts.**
On 2026-09-16 `fastapi` was gone, so the package would not even import, and
erddapy was back at 3.1.0. At the start of a session:

```bash
python -c "import erddapy; print(erddapy.__version__)"   # CI uses 3.3.1
python -c "import xpublish_erddap, xpublish"              # editable install still there?
gh auth status
```

Fix: `pip install -U erddapy && pip install -e . && pip install -r requirements-dev.txt`
(the `ioos-metrics`/`bs4` pip warning is unrelated). The hub runs
**Python 3.11**; CI tests 3.12–3.14. R has rerddap, rerddapXtracto, httr and
ncdf4 installed. **The hub cannot run Docker** (no socket, sudo blocked).
Use pre-commit's pinned ruff, not the hub's newer one. A pinned environment
is still deferred by EH.

Running the R tests locally: `python tests/server.py &`, then
`Rscript tests/test_rerddap.R` and `Rscript tests/test_tutorials.R`. Stop the
server afterwards by its PID: `pkill -f` also matches the calling shell and
exits 144.

## Working principles

- **Real ERDDAP output is now the contract, and it is tested.** Before
  changing anything in `formats.py`, `catalog.py` or `plugin.py`, run
  `tests/test_parity.py`. Several things look wrong but are ERDDAP's
  behaviour: Java number format (`4.734288E8`), float32 axes rounded to 7
  digits, case-insensitive attribute order, ties go to the larger value.
  See `notes/erddap-parity-plan.md` and `notes/client-compatibility.md`.
- **When unsure what ERDDAP does, ask a real server** (oceanwatch.pifsc.noaa.gov
  runs 2.22, erddap.ioos.us runs 2.31; use `curl -g`), then add the request
  to `tests/parity/cases.py` and recapture.
- **Test against lazily opened data.** `tests/tutorial_data.py` and the parity
  snapshots are lazy on purpose; the snapshot raises if a request reads data
  it did not capture.
- **Refuse bad axes instead of serving wrong answers** (`strict_axes`).
- **Check the pass/skip counts in the CI log**, not just the colour.
- **Validators should check client rules, not all of ERDDAP's** (#14): sorted
  unique axes matter; shared dimensions are handled by splitting; required
  globals can be defaulted. Details in `notes/erddap-parity-plan.md`.

## Notes

- `notes/erddap-parity-plan.md` — #1 end to end: which user code counts, the
  deployment model, what ERDDAP was found to do on real servers (and what is
  only inferred), how to recapture and add cases, the Copilot review
  decisions.
- `notes/client-compatibility.md` — what the clients require, version drift,
  the `importorskip` trap, ERDDAP semantics we copy.
- `notes/design-and-history.md` — direction changes, structure, `strict_axes`,
  conventions alignment.
- `notes/cefi-flux-findings.md` — CEFI groups via Flux: duplicate time values,
  mixed dimensions.
- `notes/opendap-background.md` — DAP2 and xpublish-opendap (reference for #2).
- `tools/fluxlint.py` — rough ERDDAP-readiness linter; a starting point for #14.

## Open threads (a record, not a task list)

- **Deployment blockers:** #3 (catalog cached forever) and #8 (no auth; the
  server is open to anyone).
- **#2 `.dods`:** EH chose to implement it later by reusing xpublish-opendap's
  encoder. It is no longer advertised; it answers 501 with a pointer.
  `tests/test_tutorials.py::test_erddapy_opendap_response` is a strict xfail
  that will flip when `.dods` works.
- **Raw Zarr attributes through a real ERDDAP** (Docker in GitHub Actions)
  are not covered; the parity captures are of datasets ERDDAP had already
  processed. It needs its own issue before starting.
- **Inferred, not observed:** sub-day and whole-day `averageSpacing` text, the
  `evenlySpaced` tolerance, ERDDAP adding `*most_*` globals to every dataset.
- #13/#14 hackweek proposal is waiting for collaborator feedback.
- `CODECOV_TOKEN` is not set, so the coverage badge does not work. Nothing is
  on PyPI; `publish-to-pypi.yml` has never run.
