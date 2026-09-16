"""Test ERDDAP server: the air temperature dataset plus tutorial stand-ins.

A second app is mounted at ``STORE_PREFIX``, the way one Arraylake store is
served by Flux, so its ERDDAP root is ``{STORE_PREFIX}/erddap``.
"""

import xarray as xr
import xpublish
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

rest.serve(host="0.0.0.0", port=9000)  # noqa: S104
