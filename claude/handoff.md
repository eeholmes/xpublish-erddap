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
  beside its `/opendap`. Flux is one service per protocol, routed
  `.../services/{protocol}/{org}/{repo}/{ref}/{group path}/{protocol}`, so
  that means a **per-group** root: since #18 a `dataset_router` that gets its
  data only through `deps` (as Earthmover's xpublish-tiles does), beside the
  server-wide `/erddap`. **`docs/hosting.md` is the note for Earthmover**:
  every choice a host may need to change (dataset naming, the likeliest, via
  `ErddapPlugin(name_dataset=...)`; group routing; caching on `_xpublish_id`;
  URLs). EH has it to send; Flux's real internals are still unknown.

## Repo state (2026-10-08)

- **Public test server, live until 2026-11-13:**
  https://18-119-42-78.sslip.io/erddap, `deploy/server.py` on EH's AWS
  account, running `main` at `1ea2888` (redeployed 2026-10-07). 12 stores,
  22 datasets in the server-wide root, plus one root per store at
  `/datasets/{id}/erddap`. Hackweek collaborators use it. **Tear it down on
  2026-11-13** with `deploy/aws/teardown.sh`, then revoke the Arraylake key
  (ocean-icechunks org). How to redeploy and check: `notes/flux-sim-server.md`.
  **It is behind `main`:** it lacks #56–#58 (redeploying needs EH's
  `aws login --remote` on `greenfield`).
- **Collaborator test kit, local only, deliberately not in git:**
  `collaborator-test/` on this hub (hidden by `.git/info/exclude`); EH shares
  it by Slack. Re-checked after every redeploy on 2026-10-07: 10/10 Python,
  7/7 R. Do not commit it unless EH asks.
- **Shipped 2026-10-08** (closed; decisions and reasons in
  `notes/design-and-history.md`): #55 hygiene (PR #74; a bare `pytest` now
  collects `tests/` only), #56 skip a failing source (PR #75), #57 values
  off an axis are a 404 (PR #76), #58 ERDDAP's own time/`last`/index parsing,
  `xpublish_erddap/javaparse.py` (PR #77). #78 opened on the way.
- **Shipped 2026-10-07:** #34, #18 (per-group root, `docs/hosting.md`), #3,
  #27/#4 (`search.py`, ported), #35, #36 (`errors.py`), #45/#46; 2026-10-06:
  #32, #33, #40.
- **CI, 13 checks:** the 3x3 matrix, `min-deps` (3.11, lowest versions),
  `package`, `rerddap`, pre-commit.ci. 504 passed, 42 skipped, 2 xfailed on
  Linux/macOS/min-deps; Windows 488/59/1 (skips the live-server tests). The
  skips are mostly parity media-type checks on error responses, expected.
  Parity has 4 cases now; `jplMURSST41` (coastwatch) is query parsing only
  (`metadata=False` until #78).
- The repo uses **branches and PRs**. A task stays on its branch until the
  definition of done on its issue is met. EH often says "merge #N when CI is
  green"; merged branches are deleted on GitHub and on the hub.
- #13 is the hackweek proposal; #14 (the Zarr/Icechunk validator) is its
  second project.
- **Audit done 2026-10-07 (#50, #52); its findings are issues #55–#72**, in
  the order to do them. Each says its order, dependencies, definition of done
  and which model is enough (EH asked for that; she uses Opus 5.5). Pre-release:
  #55–#67. **#55–#58 shipped 2026-10-08** (PRs #74–#77), including the three
  blockers (#56 one bad store, #57 values off an axis, #58 ERDDAP's own
  time/`last` parsing in `javaparse.py`); next is #59. #78 (integer variables
  with a `_FillValue` served as Float32) was found on the way: pre-release,
  after #59. After release: #68–#72. The ordered table is
  the last-but-one comment on #50; method and what was found fine:
  `notes/audit-2026-10.md`.

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
- **When ERDDAP's behaviour decides a question, read ERDDAP's source**
  (github.com/ERDDAP/erddap), port it, cite the class and method, and check
  it against a live server (EH asked for this on 2026-10-07). Test the
  port on more than one axis type: #57's first version was right for float64
  and wrong for float32.
- **Read query values with `javaparse.py`** (ERDDAP's lenient parsers), never
  pandas or `datetime64[ns]` (it wraps past 2262). A raw `+` arrives as a
  space on purpose; do not change `unquote_plus`.
- **CoastWatch drops requests under load (503).** `capture.py` retries them;
  retry a probe before calling a 503 a finding.

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
  norms; its plan (#32–#37) is done except #37.
- `docs/hosting.md` (not a note: public) — for Earthmover and other hosts.
- `notes/audit-2026-10.md` — #50/#52: how the audit ran, what was checked
  and found fine (so the next audit does not redo it), and the issues it made.
- `tools/fluxlint.py` — rough readiness linter; a start for #14.

## Open threads (a record, not a task list)

- **#37, first release and listing.** EH wants to talk it through first. The
  open question: release before or after donating the repo to
  xpublish-community (PyPI trusted publishing is tied to the repo owner).
  `xpublish-erddap` is free on PyPI and conda-forge (checked 2026-10-07).
  Outward steps (PyPI pending publisher, tag, conda-forge staged-recipes, the
  xpublish ecosystem PR) each need EH's yes.
- **#50 and #52 met their definition of done** (report posted, EH chose to
  open every finding as an issue). Still open; suggest closing both.
- **EH's decision (2026-10-07), not yet built:** serve latitude, longitude
  **and time** axes under ERDDAP's names by default, with an option to turn it
  off (#59).
- **#53, #54** (EH's): research ERDDAP proxying us via `EDD*FromErddap`, and
  direct Icechunk support in ERDDAP itself.
- **Earthmover:** send `docs/hosting.md`; ask how Flux registers a service,
  names its path parameters, and sets `_xpublish_id`.
- **Test server, small idea:** have `deploy/server.py` put the snapshot in
  `_xpublish_id` and reopen stores now and then, so new commits show up
  without a restart (a live demo of #3).
- **Known differences kept on purpose:** some constraint-error wording
  (stride, selector count); 400 where ERDDAP gives 500 for an unknown
  variable; `/erddap/nope` paths get FastAPI's 404. Values off an axis (404,
  #57) and index and `last` errors (400, #58) now carry ERDDAP's status and
  text. See `design-and-history.md`.
- **Other open issues:** #8 (auth), #2 (`.dods`: ~14 of ~25 current
  CoastWatch Python tutorials need it, see its latest comment), #5
  (`categorize`, now cheap: `search.categories` exists), #6, #7, #10, #14.
- **Raw Zarr attributes through a real ERDDAP** (Docker in Actions): not
  covered; needs its own issue first.
