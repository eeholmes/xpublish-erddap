"""Serve real CEFI data from Icechunk (via Earthmover Flux DAP2) as ERDDAP.

Chain demonstrated here::

    Icechunk on Arraylake
      -> Earthmover Flux DAP2
      -> xarray (pydap, lazy)
      -> xpublish + xpublish-erddap
      -> erddapy / rerddap, unmodified

In production the pydap hop would be dropped and Icechunk opened directly;
it is used here so the demo needs no Arraylake credentials.
"""
import sys, pathlib, warnings
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import xarray as xr, xpublish
from xpublish_erddap import ErddapPlugin

FLUX = (
    "https://dap2-ca2d3837a52932d4.compute.arraylake.app/v1/services/dap2/"
    "NOAA-PMEL/cefi-nep-hindcast-monthly/main/regrid/aux1/opendap"
)

print(f"opening {FLUX} ...", flush=True)
ds = xr.open_dataset(FLUX, engine="pydap", chunks={})
print(f"  {len(ds.data_vars)} variables, dims={dict(ds.sizes)}", flush=True)

# The ACDD metadata ERDDAP requires, which the Icechunk store does not carry.
# This is the equivalent of ERDDAP's datasets.xml <addAttributes>.
METADATA = {
    "title": "CEFI Northeast Pacific 10km Hindcast, Monthly-Regridded Daily Fields",
    "summary": (
        "NOAA CEFI regional ocean hindcast for the Northeast Pacific (NEP10k), "
        "regridded to a regular grid. Served from Icechunk via Earthmover Flux."
    ),
    "institution": "NOAA PMEL / GFDL",
    "infoUrl": "https://doi.org/10.5281/zenodo.13936240",
    "license": (
        "These data are made available under NOAA's open data policy. "
        "See https://doi.org/10.5194/gmd-2024-195 for the model description."
    ),
    "Conventions": "CF-1.10, COARDS, ACDD-1.3",
    "cdm_data_type": "Grid",
    "creator_name": "NOAA CEFI",
    "creator_url": "https://www.fisheries.noaa.gov/",
}

rest = xpublish.Rest(
    {"cefi_nep_hindcast_monthly": ds},
    plugins={"erddap": ErddapPlugin(metadata=METADATA)},
)
rest.serve(host="127.0.0.1", port=9700)
