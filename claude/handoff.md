# Handoff — xpublish-erddap

## What this repo is

An xpublish plugin that serves the part of ERDDAP's `griddap` REST API that
**erddapy and rerddap** use. The goal: when data moves from ERDDAP servers to
Zarr/Icechunk (for example on Earthmover Arraylake), users' existing client
code keeps working unchanged. It is **for client compatibility, not an ERDDAP
replacement**: no UI, no image output, no tabledap.

- Public at https://github.com/eeholmes/xpublish-erddap. The aim is to
  **donate it to xpublish-community**.
- **The license is BSD-3-Clause on purpose.** It matches the xpublish plugin
  family and **overrides the NOAA Apache-2.0 default** in the global
  instructions. Do not flag it or change it.
- `~/xpublish-opendap` is a **reference-only** clone of the sibling plugin.
  Do not modify it. The notes that started there were moved here 2026-09-16.

## Repo state (2026-09-16)

- All commits so far went straight to `main`;
  this repo has no PR workflow yet.
- CI is green on all 10 jobs: 3 OSes × Python 3.12–3.14, plus a Linux
  `rerddap` job. 38 tests, including live-server tests that run erddapy.
- Verified with real NOAA CEFI data read from Icechunk through Earthmover Flux.
- Issues #1–#12 hold the backlog, one task per issue. **#13 is the draft
  hackweek proposal**; EH's collaborators are reviewing it before it is
  submitted.
- A commit EH made outside these sessions, `3f60d38` (README motivation), is
  included.

## ⚠ Check the environment before trusting any local result

This is a **JupyterHub, and packages change whenever the server restarts.**
Installs from an earlier session may be gone or at different versions. At the
start of a session:

```bash
python -c "import erddapy; print(erddapy.__version__)"   # CI used 3.3.1
python -c "import xpublish_erddap, xpublish"              # editable install still there?
gh auth status                                            # was logged out after the last restart
```

**The erddapy version matters most.** erddapy ≥ 3.2 finds datasets through
`.ncml`; 3.1 uses DDS + csvp. On 2026-09-16 the local copy was back to 3.1.0
while CI used 3.3.1, so **a local pass with 3.1.0 does not test what CI and
most users run.** If needed:
`pip install -U erddapy && pip install -e . && pip install -r requirements-dev.txt`.
The same restart also removed `pre-commit` and upgraded ruff to 0.15.1. That
version flags 3 findings and 2 reformats in files that pass the ruff 0.8.6
pinned in `.pre-commit-config.yaml`. This is version drift, not a code
problem; use pre-commit's pinned version.
A separate, pinned environment (conda env or similar) is probably the real fix.
EH wants to deal with that later; it has not been started.

## Working principles

- **The clients' exact output format is the contract.** Several quirks look
  wrong but are required (uppercase `GRID`, the exact JSON content-type,
  alphabetical globals, https NcML namespace, and others). See
  `notes/client-compatibility.md` before "cleaning up" anything in
  `formats.py` or `plugin.py`.
- **Test against a lazily opened remote store**, not just tutorial data. The
  worst bug was materializing a whole remote array just to read its dtype.
- **Refuse bad axes instead of serving wrong answers** (`strict_axes`).
- **Check the pass/skip counts in the CI log.** `importorskip` once let CI pass
  with every client test skipped.

## Notes

- `notes/client-compatibility.md` — what erddapy/rerddap require, the
  version-contract problem, and what is still unverified against real ERDDAP.
- `notes/design-and-history.md` — how the direction changed, the structure and
  why, `strict_axes`, the conventions alignment (license, CI shape, what was
  deliberately not copied).
- `notes/cefi-flux-findings.md` — measurements on CEFI daily/monthly groups via
  Flux: the monthly group's duplicate time values, and the mixed dimensions
  that force a split.
- `notes/opendap-background.md` — how DAP2 and xpublish-opendap work
  (reference); the rejected "put a real ERDDAP in front" plan (historical).
- `tools/fluxlint.py` — rough ERDDAP-readiness linter for a Flux DAP2 URL. A
  starting point for the separate dataset checker in #13.

## Open threads (a record, not a task list)

- #13 hackweek proposal is waiting for collaborator feedback.
- Separate/pinned dev environment — deferred by EH.
- `CODECOV_TOKEN` secret is not set, so the coverage badge does not work.
- #1 (check output against a real ERDDAP) is the highest-value technical task;
  #3 (catalog never invalidated) and #8 (no auth — the server is currently
  open to anyone) block any real deployment.
- Nothing has been released to PyPI. `publish-to-pypi.yml` exists but has
  never run.
