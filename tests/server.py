"""Test ERDDAP server with the air temperature dataset."""

import xarray as xr
import xpublish

from xpublish_erddap import ErddapPlugin

ds = xr.tutorial.open_dataset("air_temperature")

# A second dataset whose variables do not all share the same dimensions, so the
# catalog has to split it into two ERDDAP datasets.
ds_mixed = ds.copy()
ds_mixed["air_levels"] = ds_mixed["air"].expand_dims(level=[0.0, 1.0])

rest = xpublish.Rest(
    {"air": ds, "mixed": ds_mixed},
    plugins={
        "erddap": ErddapPlugin(
            metadata={
                "title": "NCEP Reanalysis 4x Daily Air Temperature",
                "summary": "Tutorial dataset served through xpublish-erddap.",
                "institution": "NOAA ESRL PSD",
                "infoUrl": "https://psl.noaa.gov/data/gridded/data.ncep.reanalysis.html",
                "license": "[standard]",
            },
        ),
    },
)

rest.serve(host="0.0.0.0", port=9000)  # noqa: S104
