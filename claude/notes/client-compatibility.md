# Client compatibility: what erddapy and rerddap actually require

The point of this package is that **unmodified erddapy and rerddap code works**.
So the clients, and their versions, are the real specification. Everything
below was found by a client failing, and each item has a regression test. Do
not "tidy" any of it towards the DAP2 spec or FastAPI defaults.

## The contract is ERDDAP's *formatting*, not just its URL scheme

1. **erddapy (< 3.2) parses the DDS with `data.split("GRID")`.** ERDDAP writes
   uppercase `GRID`/`ARRAY`/`MAPS`; DAP2's own spelling is
   `Grid {`/`Array:`/`Maps:`. Earthmover Flux uses the DAP2 spelling, so old
   erddapy finds **zero variables** against it.
2. **rerddap asserts `content-type == "application/json;charset=UTF-8"`** —
   exact string, no space. FastAPI's default `application/json` fails. See
   `ERDDAP_JSON` in `plugin.py`.
3. **rerddap's `info()` reads `time_coverage_end`/`_start` by position**
   (`tt[2]`, `tt[1]`). That only works because ERDDAP emits `NC_GLOBAL`
   attributes **alphabetically, ignoring case** (checked against real
   servers, #1). Insertion order breaks it. ERDDAP sorts every attribute
   list this way, not only the globals.
4. **`actual_range` in text responses must be `"min, max"`**, not Python's
   `"[min, max]"`. Otherwise rerddap turns it into `NA` and then fails in
   `fix_dims`. See `attr_text()`.
5. **rerddap calls `tabledap/index.json`** to decide whether a datasetID is
   tabledap or griddap. It needs a well-formed **empty table**, not a 404.
6. **erddapy >= 3.2 finds datasets through `.ncml`**, not DDS + csvp. Its
   parser:
   - wants `<dimension>` and `<variable>` as direct children of `<netcdf>`
   - gets data variables by subtracting dimension names from variable names
   - **raises** if any dimension has no `actual_range`, and that value must be
     **space-separated** (`"min max"`, unlike item 4)
   - matches the namespace `https://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2`,
     with **https**. Older NcML documents use `http`.
7. **`.nc` output is netCDF-3 classic via `engine="scipy"`**, which is also
   what ERDDAP returns. `to_netcdf()` without a path picks whatever backend is
   installed, so the output differed between machines and broke in CI. Both
   erddapy (netCDF4 reader) and rerddap (ncdf4) are verified to read it.

Other things clients depend on: erddapy sends queries through `quote_plus`, so
the server must use `unquote_plus`. erddapy writes `min > max` for descending
axes (the tutorial `lat` goes 75 → 15), so the parser swaps a reversed range
for data-variable requests. For axis-only requests (`?latitude[(30):1:(20)]`)
ERDDAP 2.22 refuses the reversed range, and 2.31 accepts one but crashes on
two, so we refuse it with a 400.

## Client versions are part of the contract

erddapy changed how it discovers datasets between 3.1 and 3.2 (item 6). Local
work used 3.1.0; CI installed 3.3.1 from conda-forge, and every live test
failed. **A local pass says nothing about the client version CI uses.** This is
issue #10.

The environment problem that makes this worse is recorded in the handoff: this
is a JupyterHub, and packages change whenever the server restarts.

## The trap: `importorskip` can make CI pass when tests never ran

`tests/test_server.py` uses `pytest.importorskip("erddapy")`. When erddapy was
missing from `requirements-dev.txt`, every live-client test was **silently
skipped** on all nine matrix jobs, and CI still showed green. When a test job
passes, check the `passed`/`skipped` counts in the log, not just the colour.

## ERDDAP semantics we copied on purpose

- **Nearest-match ties go to the larger coordinate value**, whichever way the
  axis runs, and for time too. Checked on real servers (#11, comment there).
  So a midnight request against noon-stamped daily data now returns the
  *later* day: `2024-07-01` gives `2024-07-01T12:00Z`. (Until 2026-09-16 we
  took the first index and returned `2024-06-30T12:00Z`.)
- **A stop value is inclusive of the nearest matching step.** With 6-hourly
  data, `time<=2013-01-08T00:00Z` ends at 00:00. A pandas slice
  `"2013-01-08"` would include the whole day. This caught one of our own tests.
- **Non-monotonic axes are refused** (`strict_axes=True`), as ERDDAP does. See
  design-and-history.md for why.

## Checked against real ERDDAP servers (#1, done 2026-09-16)

`tests/test_parity.py` compares our responses with captures from oceanwatch
(ERDDAP 2.22) and erddap.ioos.us (2.31); all content comparisons match.
What that established, and what is still inferred, is in
`erddap-parity-plan.md`. Still not covered: raw Zarr attributes going
through a real ERDDAP (the captures are of datasets ERDDAP had already
processed), and tabledap.
