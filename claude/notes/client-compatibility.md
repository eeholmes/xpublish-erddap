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
   attributes **alphabetically**. Insertion order breaks it.
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
axes (the tutorial `lat` goes 75 → 15), so the parser swaps a reversed range.

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

- **Nearest-match returns the first occurrence** (`np.argmin`). A midnight
  request against noon-stamped daily data is a tie, and we return the earlier
  day: rerddap asked for `2024-07-01` and got `2024-06-30T12:00Z`. We assume
  ERDDAP does the same but have not checked (issue #11).
- **A stop value is inclusive of the nearest matching step.** With 6-hourly
  data, `time<=2013-01-08T00:00Z` ends at 00:00. A pandas slice
  `"2013-01-08"` would include the whole day. This caught one of our own tests.
- **Non-monotonic axes are refused** (`strict_axes=True`), as ERDDAP does. See
  design-and-history.md for why.

## What is still unverified

Everything above was checked against the **clients**, never against a real
ERDDAP server. We match what erddapy and rerddap happen to parse, not
necessarily what ERDDAP emits. Issue #1 (compare output file by file against a
dockerised ERDDAP) is the highest-value open task for that reason.
