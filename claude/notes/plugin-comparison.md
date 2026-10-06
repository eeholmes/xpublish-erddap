# xpublish-erddap compared with the xpublish-community plugins (#29)

Research done 2026-10-06 on shallow clones of every `xpublish-community` repo
(xpublish 0.5.2, opendap 0.2.0, zarr 0.1.0, wms 0.13.3, edr 0.9.1,
ogc-core v0.1.2, intake, intake-provider, community, .github). This note is a
report and a plan only; nothing here has been changed in the code.

## Headline

- **Our package skeleton is xpublish-opendap's**: the same setuptools_scm and
  `requirements.txt` packaging, the same pre-commit hook list, the same ruff
  rule set with Google docstrings, the same `tests.yml`, micromamba setup,
  noxfile and trusted-publishing workflow. On packaging and tooling we already
  match the closest and most established plugin. The differences that matter
  are elsewhere.
- **Two findings need EH before anything else:** a name clash (below), and
  that we ignore xpublish's one written rule for plugin authors (use the
  `deps` passed to the hook).
- **On testing we are well ahead of every plugin**: 255 tests including
  byte-level parity against real ERDDAP servers and an R client job. The
  others have about 8 to 110, mostly on `air_temperature`. Keep this; it is
  the strongest argument in a donation pitch.

## 1. Name clash: `xpublish-experiments/xpublish-erddap`

https://github.com/xpublish-experiments/xpublish-erddap exists. It was made
in 2022 by Alex Kerney (`abkfenris`), who maintains xpublish's plugin system,
and it was last pushed 2022-06-15. It is an app, not a package, and it does the
reverse of ours: it adds EDR and Zarr endpoints in front of *existing* ERDDAP
datasets. xpublish issue #138 links it. The name `xpublish-erddap` is free on
PyPI (checked: 404). The two orgs are separate, so GitHub would allow the
transfer, but two `xpublish-erddap` repos run by the same people would
confuse users.

**Alex Kerney is EH's main collaborator** (EH, 2026-10-06), so this is a
conversation between collaborators, not a cold approach to a stranger. They
can settle together whether the 2022 experiment is archived, renamed or kept,
and they are also the natural person to sponsor the donation into the org.

## 2. How the org takes plugins (explicit vs implicit)

- **Nothing is written down** for joining or transferring a repo, in
  `community`, `.github` (only a profile README and the Contributor Covenant)
  or the xpublish docs. There are no org-wide CONTRIBUTING files or templates.
- **Two tiers** (community Discussion #2, abkfenris 2023):
  `xpublish-experiments` is for things "not expected to be best practices, or
  maintained"; by implication the main org is for maintained plugins.
- **Precedent:** Discussion #12 offered to transfer xpublish-file-metadata
  "once things are stable", posted under Show and tell; it never moved.
  Discussion #19 (wish list) names "interoperability with legacy systems
  (THREDDS/ERDDAP)", which is exactly our pitch.
- **Where people talk:** GitHub Discussions in `xpublish-community/community`
  (quiet since 2024-12, the last monthly meeting notes) and `#xpublish` on
  ESIP Slack. Recent activity is all in PRs. The docs say to tag `@abkfenris`
  for help with the plugin system.
- **Getting listed:** `docs/source/ecosystem/index.md` in xpublish has a
  bullet per plugin with PyPI and conda-forge badges. No process; inferred
  route is a PR adding a bullet, after a PyPI release.
- **License:** no org norm. BSD-3 (opendap, wms, edr, intake-provider) and
  Apache-2.0 (core, zarr, ogc-core) coexist. Our BSD-3 fits.
- **Naming:** `xpublish-<x>` repo and distribution, `xpublish_<x>` module,
  entry point in `xpublish.plugin`. We match.

## 3. Plugin structure

| | opendap | zarr | wms | edr | **erddap** |
|---|---|---|---|---|---|
| hook | dataset_router | dataset_router | dataset_router | app + dataset + ogc-core hooks | **app_router** |
| dataset access | `Depends(deps.dataset)` | same | same | same | **`app.dependency_overrides`** |
| cache | cachey, cost 99999 | cachey, CostTimer | cachey | none | cachey, cost 99999 |
| query parsing | opendap-protocol | path only | pydantic model, discriminated union | pydantic models, `Field(description=)` | hand-written parser (`constraints.py`) |
| formats | fixed | fixed | fixed per operation | **entry-point groups** | fixed dispatch in `griddap()` |
| error bodies | none | FastAPI default | FastAPI default | **OGC JSON via custom `APIRoute`** | FastAPI default |
| plugin fields | plain | plain | plain | plain | plain, `#:` comments |

Findings:

- **We ignore `deps`.** `app_router(self, deps)` carries `# noqa: ARG002` and
  calls `xpublish.dependencies.get_dataset` and friends through
  `request.app.dependency_overrides` (`plugin.py`, `_resolve`). xpublish's
  plugin guide says plugins "should use `xpublish.Dependencies.dataset` rather
  than directly importing `xpublish.dependencies.get_dataset`", so that a
  caller can hand a router different dependencies. The reason we do it is
  recorded (`design-and-history.md`: an app router has no `{dataset_id}` in
  its path, so `Depends(deps.dataset)` cannot be used), and it is a real
  reason. But the fix is small and keeps the reason: resolve `deps.dataset`,
  `deps.dataset_ids` and `deps.cache` through the overrides instead of the
  module-level functions.
- **xpublish 0.5 changed the data model under us.** Since 0.5.0 (2026-05)
  everything published is an `xarray.DataTree`, and routes opt in to groups
  with a `{group_path:path}` segment; `deps.dataset` then returns that node.
  This is directly relevant to #18 (a per-group `/erddap`), and possibly to how
  `build_catalog` names datasets for Zarr groups. We still declare
  `xpublish>=0.4.0` while CI installs xpublish `main`, so the floor is never
  tested.
- **We are the only app_router-centred plugin**, apart from ogc-core's
  catalog. That is right for ERDDAP (one root, many datasetIDs) and is already
  argued in the notes; it is worth one sentence in the pitch, because every
  other plugin is per-dataset.
- **Error bodies.** Real ERDDAP answers `Error {\n    code=...;\n
  message="...";\n}` as text; we answer FastAPI's `{"detail": "..."}`. Parity
  tests check only the status on errors. ogc-core shows the community way to
  shape them (an `APIRoute` subclass catching `HTTPException` and
  `RequestValidationError`). Whether it matters depends on whether erddapy,
  rerddap or users' code read the body; that is unchecked.
- **Formats as entry points (edr)** is a nice pattern, but ERDDAP's file-type
  list is fixed by ERDDAP, not open-ended. Not worth copying.
- **Pydantic query models (wms, edr)** do not suit ERDDAP's raw
  `var[a:b:c][...]` grammar, which is not key=value. Our parser is the right
  shape. The search endpoints, which *are* key=value, could use `Query()`
  parameters with descriptions for the OpenAPI page; cosmetic.

## 4. Tooling and CI

| | core | opendap | zarr | edr | **erddap** |
|---|---|---|---|---|---|
| build | setuptools_scm | setuptools_scm | hatch-vcs | setuptools_scm | setuptools_scm |
| deps | inline + dep-groups | requirements.txt | inline + uv | inline + dep-groups | requirements.txt |
| ruff line length | 100 | 88 | 100 | 100 | 88 |
| docstrings | Google | Google | Google | free-form | Google |
| mypy | no | pre-commit hook | no | configured, not run | no |
| extra hooks | zizmor, repo-review, pyproject-fmt | mypy, codespell | pyproject-fmt | zizmor, repo-review, codespell | codespell |
| CI matrix | ubuntu 3.11–3.14 + upstream + min-deps | 3 OS × 3.12–3.14 | ubuntu 3.11–3.13 | 3 OS × 3.12–3.14 | 3 OS × 3.12–3.14 + R |
| actions | SHA-pinned, `permissions: {}` | old tags | tags | SHA-pinned | tags |
| pre-commit.ci | yes | yes | yes | yes | **no** |
| PyPI | trusted, on release | trusted | trusted | trusted | trusted (never run) |

The direction of travel (core, edr, ogc-core) is: ruff at line length 100,
PEP 735 `[dependency-groups]`, uv, pre-commit.ci, zizmor and repo-review,
SHA-pinned actions with minimal `permissions`, an upstream job and a min-deps
job. Only core uses single quotes; do not copy that. No plugin has a
CHANGELOG, CONTRIBUTING or code of conduct (the org CoC covers them), so those
are not expected.

Our pre-commit revs are well behind opendap's (ruff v0.8.6 against
v0.14.14). `requires-python >=3.11` but CI starts at 3.12.

## 5. Code style, given that Claude wrote it

Measured on `xpublish_erddap/` (1,776 lines):

**What reads well, and is in line with the best of the community (zarr,
edr):**

- Every module has a docstring explaining *why* it exists; comments explain
  ERDDAP behaviour that would otherwise look like bugs (Java number
  formatting, the exact rerddap content-type string, ERDDAP's 413 wording).
  This density is higher than opendap's but matches zarr and edr, and it is
  what a reviewer of protocol-mimicking code needs.
- `constraints.py`, `formats.py` and `catalog.py` are small pure functions
  over plain dataclasses, easy to test, and they are tested.
- Only 8 `noqa`s in the package, all justified (6 in `plugin.py`).

**What a community reviewer would likely flag:**

- **`ErddapPlugin.app_router` is one ~300-line function** holding every
  route plus helpers (`catalog`, `lookup`, `_table`, `_csv_cell`, `_search`)
  as closures; it needs `# noqa: PLR0915`. opendap's and zarr's
  whole `plugin.py` files are 101 and 135 lines, and wms keeps its hook to one
  route that dispatches into per-operation modules. The helpers need only
  `plugin` and the request, so they can be module-level functions or a small
  class, leaving the hook as route declarations.
- **Dead or loose bits:** `logger` defined but unused in `plugin.py`; `_table`
  takes a `name` argument it never uses; `plugin.py` calls the private
  `formats._dtype_of` (with `# noqa: SLF001`); the `ed` argument is untyped
  throughout `formats.py` (29 untyped arguments in the package, by ruff
  ANN001), where `ErddapDataset` would document it.
- **The `deps` bypass** (section 3), which is the one place the code goes
  against written guidance.
- The README still calls it a "Prototype" and "proof of concept"; fine now,
  but it should say what is stable before a donation.

None of these is a defect in behaviour. The pattern is typical of code grown
feature-by-feature in one file: correct, well-commented, tested, but with one
function that collected everything.

## 6. Plan (proposed; each is a separate issue, nothing coded under #29)

Ordered by what blocks a donation first.

1. **Settle the name and the route with Alex Kerney first.** They are EH's
   main collaborator, made the 2022 experiment, and maintain the plugin
   system. Agree on what happens to the experiment repo and on how a donation
   should go. A public Show-and-tell Discussion in
   `xpublish-community/community` (and ESIP `#xpublish`) can follow, if the
   org wants a public record. *EH's call.*
2. **Use `deps` as xpublish documents** (small; code issue). Resolve
   `deps.dataset`, `deps.dataset_ids`, `deps.cache` through the overrides,
   drop the `ARG002` noqa, add a test that a custom `Dependencies` is
   honoured.
3. **Move to xpublish ≥0.5 and design for DataTree** (medium; fold into #18).
   Decide how Zarr groups map to ERDDAP datasetIDs now that xpublish models
   groups itself; set the floor to `>=0.5` and add a min-deps CI job so it is
   tested.
4. **Split `app_router`** (small refactor; parity tests guard it). Helpers to
   module level, remove the unused logger and argument, make `_dtype_of`
   public, type `ed`.
5. **Tooling refresh** (small, mechanical): ruff line length 100, bump hook
   revs, add pre-commit.ci (`ci:` block) and zizmor, pin actions by SHA with
   `permissions: {}`, run build + `check-manifest` on PRs, align the CI matrix
   with `requires-python`. Leave packaging (setuptools_scm,
   `requirements.txt`) as is; it matches opendap and wms.
6. **ERDDAP-shaped error bodies** (investigate first): check whether erddapy
   or rerddap surface the body; if so, copy ogc-core's `APIRoute` pattern and
   make parity tests compare error text.
7. **After a PyPI release:** conda-forge recipe, PyPI/conda badges, PR to
   xpublish's `ecosystem/index.md`. README: an endpoint table like zarr's and
   a line on how this differs from the 2022 experiment.

Explicitly **not** proposed: switching to hatchling or uv, a src/ layout,
pydantic query models for griddap, formats as entry points, single quotes,
CONTRIBUTING/CHANGELOG files. None is a community norm, and each would be
churn.
