"""Test server: xarray's air_temperature tutorial dataset over the ERDDAP API."""

import xarray as xr
import xpublish

from xpublish_erddap import ErddapPlugin

ds = xr.tutorial.open_dataset("air_temperature")
ds.attrs.update(
    {
        "title": "NCEP Reanalysis 4x Daily Air Temperature",
        "summary": "Tutorial air temperature dataset served through xpublish-erddap.",
        "institution": "NOAA ESRL PSD",
        "infoUrl": "https://psl.noaa.gov/data/gridded/data.ncep.reanalysis.html",
        "license": "[standard]",
    },
)
rest = xpublish.Rest({"air_temp": ds}, plugins={"erddap": ErddapPlugin()})
rest.serve(host="127.0.0.1", port=9500)
