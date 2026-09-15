# xpublish-erddap

[![tests](https://github.com/eeholmes/xpublish-erddap/actions/workflows/tests.yml/badge.svg)](https://github.com/eeholmes/xpublish-erddap/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Prototype.** An ERDDAP-compatible `griddap` router for [Xpublish](https://github.com/xpublish-community/xpublish),
so that existing **[erddapy](https://ioos.github.io/erddapy/)** and
**[rerddap](https://docs.ropensci.org/rerddap/)** code keeps working when the data
moves to Zarr/Icechunk.

The goal is *client compatibility*, not an ERDDAP replacement. There is no Data
Access Form, no Make-A-Graph, and no tabledap — just the REST surface those two
client libraries actually call, so users' scripts run unchanged against an
Xpublish server.

```
Icechunk / Zarr / any xarray Dataset
  -> xpublish + xpublish-erddap
  -> erddapy / rerddap, unmodified
```

## Status

Working end to end against both clients, on synthetic data and on real NOAA CEFI
model output served from Icechunk via Earthmover Flux. Not production software:
no auth, no tabledap, a partial file-type list, and the catalog is built eagerly
at first request.

## Usage

```python
import xarray as xr, xpublish
from xpublish_erddap import ErddapPlugin

ds = xr.open_zarr("...")            # or icechunk, or anything xarray opens

rest = xpublish.Rest(
    {"my_dataset": ds},
    plugins={"erddap": ErddapPlugin(metadata={
        # ERDDAP requires these; most Zarr stores do not carry them.
        # This is the equivalent of ERDDAP's datasets.xml <addAttributes>.
        "title": "My Dataset",
        "summary": "...",
        "institution": "...",
        "infoUrl": "https://example.org",
        "license": "[standard]",
    })},
)
rest.serve(port=9000)
```

Then, unchanged client code:

```python
from erddapy import ERDDAP
e = ERDDAP(server="http://localhost:9000/erddap", protocol="griddap", response="nc")
e.dataset_id = "my_dataset"
e.griddap_initialize()
e.constraints.update({"time>=": "2024-07-01", "time<=": "2024-07-05"})
ds = e.to_xarray()
```

```r
library(rerddap)
i <- info("my_dataset", url = "http://localhost:9000/erddap/")
d <- griddap("my_dataset", url = "http://localhost:9000/erddap/",
             time = c("2024-07-01", "2024-07-05"), fields = "tos")
```

## What is implemented

| Endpoint | Purpose |
| --- | --- |
| `/erddap/griddap/{id}.{ext}?{query}` | data; `ext` in `nc, csv, csvp, csv0, json, das, dds` |
| `/erddap/griddap/index.{csv,json}` | dataset catalog |
| `/erddap/tabledap/index.{csv,json}` | empty catalog (rerddap needs it to classify a dataset) |
| `/erddap/info/{id}/index.{csv,json}` | variable and attribute table |
| `/erddap/search/index.{csv,json}`, `/erddap/search/advanced.{csv,json}` | free-text search |
| `/erddap/version` | version banner |

Constraint syntax: coordinate values `[(2024-07-01):1:(2024-07-05)]`, integer
indices `[0:1:10]`, strides, `last` / `last-N` / `(last)` / `(last-N)`, and the
`[start:stop]` / `[start]` / `[]` shorthands.

## Notes for anyone extending this

ERDDAP clients are coupled to ERDDAP's exact *formatting*, not just its URL
scheme. Four cases found the hard way, all covered by tests:

1. `erddapy` parses the DDS with `data.split("GRID")`, so `GRID`/`ARRAY`/`MAPS`
   must be uppercase — DAP2's own spelling (`Grid {`) yields zero variables.
2. `rerddap` asserts `content-type == "application/json;charset=UTF-8"` exactly.
3. `rerddap`'s `info()` reads `time_coverage_end`/`_start` *positionally*, which
   only works because ERDDAP emits `NC_GLOBAL` attributes alphabetically.
4. `actual_range` must be rendered `"min, max"`, not Python's `"[min, max]"`,
   or `rerddap` silently coerces it to `NA`.

Two further constraints are structural rather than cosmetic:

**One hypercube per dataset.** An ERDDAP dataset has a single set of axes that
every data variable shares, so a source whose variables have differing
dimensions maps to *several* ERDDAP datasets. `catalog.build_catalog` does that
split, suffixing the extra datasets with their distinguishing dimension. Tested
against a real CEFI group of 92 variables, which splits into three.

**Axes must be strictly monotonic.** ERDDAP refuses a dataset whose axes are
not, and so does this package (`strict_axes=True`, the default), logging which
axis broke and where. Serving such data anyway is worse than refusing it:
coordinate-value requests still look correct, because nearest-match lands on the
first occurrence, while index ranges spanning the break silently return a series
that jumps backwards in time. Pass `strict_axes=False` to override.

## Demos

`demo/serve_air.py` serves xarray's tutorial dataset; `demo/serve_cefi.py`
serves real NOAA CEFI output read from Earthmover Flux. `demo/demo_rerddap.R`
and `demo/demo_cefi.R` exercise the R client.

## Reuse and citation

This work is released under [Apache-2.0](LICENSE). You are free to use, copy,
modify, and redistribute it, including commercially. If you use it in published
work, in a presentation, or in another repository, please give attribution:

> Holmes, E.E. (2026). *xpublish-erddap: ERDDAP-compatible griddap router for Xpublish*.
