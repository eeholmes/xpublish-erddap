"""Test ERDDAP server: the air temperature dataset plus tutorial stand-ins.

A second app is mounted at ``STORE_PREFIX``, the way one Arraylake store is
served by Flux, so its ERDDAP root is ``{STORE_PREFIX}/erddap``. A third, at
``FLUX_PREFIX``, routes by org, repo, ref and group as Flux does
(``flux_host.py``), so each group has its own ERDDAP root.
"""

import xarray as xr
import xpublish
from flux_host import FLUX_PREFIX, FluxLikeRest
from tutorial_data import (
    STORE_PREFIX,
    STORE_SOURCE_ID,
    store_dataset,
    tutorial_datasets,
)

from xpublish_erddap import ErddapPlugin

ds = xr.tutorial.open_dataset("air_temperature")
# Set on the dataset, not as plugin metadata, which applies to every dataset.
ds.attrs.update(
    {
        "title": "NCEP Reanalysis 4x Daily Air Temperature",
        "summary": "Tutorial dataset served through xpublish-erddap.",
        "institution": "NOAA ESRL PSD",
        "infoUrl": "https://psl.noaa.gov/data/gridded/data.ncep.reanalysis.html",
        "license": "[standard]",
    },
)

# A second dataset whose variables do not all share the same dimensions, so the
# catalog has to split it into two ERDDAP datasets.
ds_mixed = ds.copy()
ds_mixed["air_levels"] = ds_mixed["air"].expand_dims(level=[0.0, 1.0])

rest = xpublish.Rest(
    {"air": ds, "mixed": ds_mixed, **tutorial_datasets()},
    plugins={"erddap": ErddapPlugin()},
)

store = xpublish.Rest(
    {STORE_SOURCE_ID: store_dataset()},
    plugins={"erddap": ErddapPlugin()},
)
rest.app.mount(STORE_PREFIX, store.app)

# Flux's routing: the same store as a tree, one ERDDAP root per group at
# {FLUX_PREFIX}/NOAA-PMEL/cefi-nep-hindcast-daily/main/regrid/main/erddap.
flux = FluxLikeRest(
    {
        "NOAA-PMEL/cefi-nep-hindcast-daily": xr.DataTree.from_dict(
            {"/regrid/main": store_dataset()},
        ),
    },
    plugins={"erddap": ErddapPlugin()},
)
rest.app.mount(FLUX_PREFIX, flux.app)

rest.serve(host="127.0.0.1", port=9000)
