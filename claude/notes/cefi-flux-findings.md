# CEFI data and Earthmover Flux: measured findings

Measured 2026-09-15 against real public Flux endpoints. These are measurements,
not predictions. Moved here 2026-09-16.

**Still valid:** the endpoint facts, the confirmation that Flux uses
xpublish, both data blockers, and the daily-vs-monthly comparison.
**Out of date:** the "Situation" and "Proposed hackweek shape" sections. They
assumed we would put a real ERDDAP in front of Flux. We are building this
package instead (design-and-history.md), and the hackweek proposal is
issue #13. How the blockers were then handled in code: blocker 2 is split
automatically by `build_catalog`, and blocker 1 is refused by `check_axes`.

## Situation (OUT OF DATE — kept for context)

EH has **no ERDDAP server**. The data is Icechunk on Earthmover Arraylake, and
it is *already* served over OPeNDAP by **Earthmover Flux**. So there is nothing
to build on the Icechunk->DAP side; xpublish-opendap will not be deployed. The
only thing to build is ERDDAP in front of Flux.

Earthmover has **not** fronted Flux with ERDDAP yet (confirmed by EH). EH is
writing a **hackweek proposal** to make progress on the ERDDAP piece. That is
the active goal — these findings are evidence for that proposal.

## Endpoint tested

    https://dap2-ca2d3837a52932d4.compute.arraylake.app/v1/services/dap2/
      NOAA-PMEL/cefi-nep-hindcast-monthly/main/regrid/aux1/opendap

Public, no auth needed. Note the host is a per-service
`dap2-<hash>.compute.arraylake.app`, not the `compute.earthmover.io` in the
docs. General Flux schema:
`/v1/services/dap2/{org}/{repo}/{branch|commit|tag}/{path/to/group}/opendap`.
Auth elsewhere is HTTP Basic, username = org, password = Arraylake API token,
embeddable as `https://{org}:{token}@...` (which is what makes ERDDAP's
`<sourceUrl>` able to reach a private repo at all — ERDDAP has no first-class
credential config for EDDGridFromDap).

## CONFIRMED: Flux DAP2 is xpublish

`NC_GLOBAL` contains:

    String _xpublish_id "NOAA-PMEL/cefi-nep-hindcast-monthly/8XKCSPYD2P8FG4M59BBG/regrid/aux1";

So Flux runs this repo's pattern, with an Icechunk-aware dataset provider — note
the snapshot ID embedded in that string, which is how they avoid the
stale-snapshot problem a static `Rest({"id": ds})` would have. The earlier
"unverified" caveat about Earthmover using xpublish can now be dropped for the
DAP2 service specifically.

## What works (measured)

- `.dds`, `.das`, `.dods` all return 200 with well-formed DAP2.
- Grid structures with proper `Maps`; `time` is the leftmost dimension, which is
  what ERDDAP wants.
- Server-side subsetting honours constraints:
  `tos[0:1:1][100:1:102][200:1:202]` -> 597 bytes in 0.7 s.
- `xr.open_dataset(url, engine="pydap")` opens all 92 data vars; `time` decodes
  to `datetime64[ns]`.
- `NC_GLOBAL` is rich: title, full CEFI provenance, data DOI and paper DOI.
- `lat`/`lon` carry `standard_name`, `units`, `axis`, `actual_range`.

Gotcha when testing by hand: `curl` globs `[` and `]`. Use `curl -g` or the
request fails with "bad range in URL" and looks like a server error.

## BLOCKER 1 — time axis is not strictly monotonic

Decoded the full axis from `.dods?time`: **396 values, only 390 unique.**

    i=389   11854.0 (2025-06-16)  ->  11703.5 (2025-01-16)   step=-150.5

The six months Jan–Jun 2025 are duplicated and appended after the clean
1993-01 -> 2025-06 monthly series. ERDDAP requires strictly monotonic axis
values and will **refuse to load the dataset**.

This is a **data problem in the Icechunk store** — an append that should have
been an overwrite — not a Flux or an ERDDAP problem. xarray opens it without
complaint, which is precisely why it went unnoticed. Fix is one Icechunk commit
at the source.

## BLOCKER 2 — mixed dimensionality within one group

Of 92 data variables in this group:

- 90 are `[time][lat][lon]`
- 1 (`rhoinsitu`) is `[time][z_l][lat][lon]`
- 1 (`CN`) is `[time][ct][lat][lon]`

ERDDAP docs are explicit: in EDDGrid datasets all data variables must share
*all* axis variables; differing dimensions require separate datasets. So this
one Flux group must become **three** ERDDAP datasets.

**This is the deep impedance mismatch and the most interesting thing for the
hackweek to solve generically:** a Zarr/Icechunk group is a bag of variables
that need not share dimensions; an ERDDAP griddap dataset is a single
rectangular hypercube. The mapping is one-to-many and must be derived, not
hand-written.

## LIKELY ISSUE 3 — bare `nan` literal in DAS (untested)

    time { ... Float64 _FillValue nan; }

Two risks: ERDDAP's Java DAS parser may reject the bare `nan` token, and a
`_FillValue` on a coordinate axis is semantically wrong anyway. Overridable in
datasets.xml. Test early — a DAS parse failure surfaces as an opaque error.

## Metadata gap — not a blocker, but it is the workload

Absent and required by ERDDAP: `summary`, `institution`, `infoUrl`, `license`,
`Conventions`, `cdm_data_type` globally; `ioos_category` on all 92 variables.
All injectable via `<addAttributes>`, so the Icechunk store stays clean — but by
hand that is ~500 lines of XML for **one** group, times three datasets, times
however many CEFI groups exist. Hence the generator below.

## Proposed hackweek shape (OUT OF DATE — see issue #13)

This was written when the plan was a real ERDDAP in front of Flux. Item 2, the
readiness linter, is still wanted; it is the "dataset checker/validator" work
stream in issue #13, and it is **separate from this package**. The rest has
been dropped.

Weak version: "stand up an ERDDAP in front of Flux." Strong version, which the
findings above justify:

1. **`flux2erddap` generator** — read a group's `.das`/`.dds`, emit ERDDAP
   `datasets.xml`: partition variables by dimension signature into separate
   `<dataset>` blocks, map CF `standard_name`/`units` -> `ioos_category`, fill
   ACDD gaps from config, embed Basic-auth credentials in `sourceUrl`.
2. **Readiness linter** — check monotonic axes, duplicate coordinates, NaN
   attribute literals, mixed dimensionality, missing ACDD, *before* ERDDAP sees
   it. Both blockers above would have been caught in seconds.
3. **One end-to-end proof** — dockerised ERDDAP, one CEFI dataset, erddapy *and*
   rerddap notebooks showing unchanged user code.
4. **Feedback to Earthmover** — EH would be first to do this; items 1–2 are what
   Earthmover would need to offer ERDDAP as a fourth Flux protocol.

## SECOND GROUP TESTED — the blockers are per-group, not systemic

Also tested `cefi-nep-hindcast-daily/main/regrid/main`. Result: **clean on both
blockers.** Side by side:

| check | daily / regrid/main | monthly / regrid/aux1 |
|---|---|---|
| multi-dim signatures | **1** — `[time][lat][lon]`, 14 vars | **3** — 90x `[time][lat][lon]`, `CN` `[time][ct][lat][lon]`, `rhoinsitu` `[time][z_l][lat][lon]` |
| time axis | **OK** n=11869, 11869 unique, ascending | **FAIL** n=396, 390 unique, breaks at i=389 |
| other axes | lat/lon OK | ct, z_l, lat, lon all OK |
| bare `nan` attr | 1 (`_FillValue` on time) | 1 (`_FillValue` on time) |
| missing ACDD globals | summary, institution, infoUrl, license, Conventions, cdm_data_type | same |
| vars with `ioos_category` | 0 of ~14 | 0 of ~92 |

**This is the most important finding for the proposal.** Blockers 1 and 2 are
*data-quality issues in specific groups*, not systemic problems with the
Flux -> ERDDAP path. The daily group would map to a single ERDDAP dataset today
with nothing but metadata injection.

Consequences:
- Use **`cefi-nep-hindcast-daily/main/regrid/main` as the end-to-end proof
  target** — it is the one already known to be ready.
- The monthly `aux1` duplicate-time bug is worth reporting to whoever builds the
  CEFI Icechunk stores regardless of the ERDDAP work; it is a real defect that
  xarray silently tolerates.
- The linter earns its place: it is how you tell ready groups from unready ones
  without standing up ERDDAP for each.

A first cut of that linter is in `claude/tools/fluxlint.py` in this repo (usage:
`python fluxlint.py <dap2-base-url> [...]`; it takes several base URLs and
prints the table above per group). It is rough — regex over DDS/DAS, no auth
support yet — but it found both blockers.

## Limits of this testing — be honest about these in the proposal

- Two groups on two repos. The spread across *all* CEFI groups is still
  unmeasured — run the linter over the full list to quantify it.
- **No ERDDAP has actually been put in front of Flux** (and that plan was
  later shelved). Issue 3 and any wider
  DAS-parser strictness remain untested. Blockers 1 and 2 are certain; the
  absence of *further* blockers is not established.
- Security, for when a private repo is used: a default ERDDAP is public, and the
  Arraylake token would sit in plaintext in datasets.xml. Lock the file down,
  use a dedicated minimally-scoped API client, and decide deliberately whether
  the ERDDAP is public (`<authentication>` in setup.xml, `<accessibleTo>` per
  dataset).
