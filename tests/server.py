"""Test ERDDAP server: the air temperature dataset plus tutorial stand-ins."""

import xarray as xr
import xpublish
from tutorial_data import tutorial_datasets

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

rest.serve(host="0.0.0.0", port=9000)  # noqa: S104
