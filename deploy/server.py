"""A Flux-like xpublish server: Icechunk stores behind OPeNDAP and ERDDAP.

Earthmover Flux serves Arraylake Icechunk stores with xpublish and the stock
xpublish-opendap plugin. This server does the same, adds xpublish-erddap beside
it, and serves two kinds of public Icechunk store:

- ``cefi_*``: seven NOAA CEFI stores on Arraylake (``NOAA-PMEL/cefi-*``; see
  ``CEFI`` below). Virtual stores; their chunks are CEFI NetCDF files in
  NODD. The repos are public to any Arraylake account, so the server needs an
  Arraylake login or API token.
- ``gobai_o2_monthly``: plain Icechunk on S3 (Source Cooperative,
  ``fish-pace/gobai-o2/monthly``), read anonymously.

Routes::

    /erddap/...                    one ERDDAP root listing every dataset
    /datasets/{id}/opendap.dds     stock xpublish-opendap, per dataset

Flux is one app too, but routes by store and group:
``.../{org}/{repo}/{ref}/{group path}/opendap``. ErddapPlugin cannot sit beside
each group yet (#18), so this server has a single ``/erddap`` root instead.
Stock xpublish-opendap also mis-reads DAP strides (see #2); Flux does not.

Stores are opened in the background at startup (or on first request, if that
comes sooner) and pinned to the snapshot ``main`` pointed at then. New commits
are not picked up until a restart (#3).

Run::

    python deploy/server.py                 # http://127.0.0.1:9100
    HOST=0.0.0.0 PORT=8000 python deploy/server.py

Data requests over ``MAX_RESPONSE_MB`` (default 500) get ERDDAP's 413.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from functools import cache, partial

import icechunk
import uvicorn
import xarray as xr
import xpublish
from xpublish import Plugin, hookimpl
from xpublish_opendap import OpenDapPlugin

from xpublish_erddap import ErddapPlugin

log = logging.getLogger("flux_sim")


#: CEFI stores on Arraylake (NOAA-PMEL org, ref ``main``), as served by Flux:
#: dataset id -> (repo, group, title, what the summary says about it).
#: The repos are public to any Arraylake account.
CEFI: dict[str, tuple[str, str, str, str]] = {
    "cefi_nep_hindcast_daily": (
        "cefi-nep-hindcast-daily",
        "regrid/main",
        "CEFI Northeast Pacific 10 km Hindcast, Daily, Regridded",
        "hindcast for the Northeast Pacific, daily, regridded to a regular "
        "latitude-longitude grid",
    ),
    "cefi_nep_hindcast_monthly": (
        "cefi-nep-hindcast-monthly",
        "regrid/main",
        "CEFI Northeast Pacific 10 km Hindcast, Monthly, Regridded",
        "hindcast for the Northeast Pacific, monthly means, regridded to a "
        "regular latitude-longitude grid",
    ),
    "cefi_nep_hindcast_monthly_raw": (
        "cefi-nep-hindcast-monthly",
        "raw/main",
        "CEFI Northeast Pacific 10 km Hindcast, Monthly, Native Model Grid",
        "hindcast for the Northeast Pacific, monthly means, on the model's "
        "native curvilinear grid (index axes; latitude and longitude are the "
        "geolat and geolon variables)",
    ),
    "cefi_nwa_hindcast_monthly_raw": (
        "cefi-nwa-hindcast-monthly",
        "raw/main",
        "CEFI Northwest Atlantic 12 km Hindcast, Monthly, Native Model Grid",
        "hindcast for the Northwest Atlantic, monthly means, on the model's "
        "native curvilinear grid (index axes; latitude and longitude are the "
        "geolat and geolon variables)",
    ),
    "cefi_nwa_decadal_forecast_monthly_i196501": (
        "cefi-nwa-decadal-forecast-monthly",
        "regrid/i196501",
        "CEFI Northwest Atlantic Decadal Forecast from January 1965, Monthly, "
        "Regridded",
        "10-member decadal forecast for the Northwest Atlantic, initialized "
        "January 1965, monthly means over a 10-year lead, regridded to a "
        "regular latitude-longitude grid",
    ),
    "cefi_nwa_decadal_forecast_yearly_i196501": (
        "cefi-nwa-decadal-forecast-yearly",
        "regrid/i196501",
        "CEFI Northwest Atlantic Decadal Forecast from January 1965, Yearly, "
        "Regridded",
        "10-member decadal forecast for the Northwest Atlantic, initialized "
        "January 1965, yearly means over a 10-year lead, regridded to a "
        "regular latitude-longitude grid",
    ),
    "cefi_nwa_seasonal_reforecast_monthly_i199401": (
        "cefi-nwa-seasonal-reforecast-monthly",
        "regrid/i199401",
        "CEFI Northwest Atlantic Seasonal Reforecast from January 1994, Monthly, "
        "Regridded",
        "10-member seasonal reforecast for the Northwest Atlantic, initialized "
        "January 1994, monthly means at leads of 0-11 months, regridded to a "
        "regular latitude-longitude grid",
    ),
}


def _open_cefi(dataset_id: str) -> tuple[xr.Dataset, str]:
    from arraylake import Client  # noqa: PLC0415  (only these stores need it)

    repo_name, group, title, about = CEFI[dataset_id]
    session = Client().get_repo(f"NOAA-PMEL/{repo_name}").readonly_session("main")
    ds = xr.open_zarr(session.store, group=group, consolidated=False, chunks={})
    # On the native grids, latitude and longitude are 2-D coordinates
    # (geolat, geolon). Serve them as variables, as ERDDAP does for a
    # curvilinear grid, or no one could tell where a cell is.
    ds = ds.reset_coords([name for name, c in ds.coords.items() if c.ndim >= 2])  # noqa: PLR2004
    # ACDD attributes ERDDAP clients expect and the store does not carry, the
    # counterpart of <addAttributes> in an ERDDAP datasets.xml. The store's
    # own title is the model run name, which no one would search for.
    ds.attrs.update(
        {
            "title": title,
            "summary": (
                f"NOAA CEFI MOM6-COBALT regional ocean model {about}. Served "
                f"from a virtual Icechunk store on Arraylake (NOAA-PMEL/"
                f"{repo_name}, group {group})."
            ),
            "institution": "NOAA CEFI",
            "infoUrl": f"https://doi.org/{ds.attrs['cefi_data_doi']}",
            "license": "CC-BY-4.0",
            "Conventions": "CF-1.10, COARDS, ACDD-1.3",
            "cdm_data_type": "Grid",
        },
    )
    return ds, session.snapshot_id


def _open_gobai() -> tuple[xr.Dataset, str]:
    storage = icechunk.s3_storage(
        bucket="us-west-2.opendata.source.coop",
        prefix="fish-pace/gobai-o2/monthly",
        region="us-west-2",
        anonymous=True,
    )
    session = icechunk.Repository.open(storage).readonly_session("main")
    ds = xr.open_zarr(session.store, consolidated=False, chunks={})
    # The store is ACDD-complete except for these.
    ds.attrs.update(
        {
            "institution": ds.attrs.get("creator_institution", "NOAA PMEL"),
            "infoUrl": "https://www.pmel.noaa.gov/gobai/",
            "cdm_data_type": "Grid",
        },
    )
    return ds, session.snapshot_id


#: Dataset id -> function that opens it lazily and returns (dataset, snapshot).
STORES: dict[str, Callable[[], tuple[xr.Dataset, str]]] = {
    **{dataset_id: partial(_open_cefi, dataset_id) for dataset_id in CEFI},
    "gobai_o2_monthly": _open_gobai,
}


@cache
def open_store(dataset_id: str) -> xr.Dataset:
    """Open a store once and keep it; record the snapshot it was pinned to."""
    ds, snapshot = STORES[dataset_id]()
    ds.attrs["icechunk_snapshot"] = snapshot
    log.info("opened %s at snapshot %s", dataset_id, snapshot)
    return ds


class IcechunkProvider(Plugin):
    """Dataset provider plugin, the way Flux supplies datasets to xpublish."""

    name: str = "icechunk-provider"

    @hookimpl
    def get_datasets(self):
        """Ids of every store this server can open."""
        return list(STORES)

    @hookimpl
    def get_dataset(self, dataset_id: str):
        """Open the store on first use; ``None`` lets other providers try."""
        if dataset_id not in STORES:
            return None
        return open_store(dataset_id)


def make_app():
    """Build the xpublish app with the provider, OPeNDAP and ERDDAP plugins."""
    rest = xpublish.Rest(
        {},
        plugins={
            "icechunk-provider": IcechunkProvider(),
            "opendap": OpenDapPlugin(),
            # A public server must cap what one request can pull (#16).
            "erddap": ErddapPlugin(
                max_response_mb=float(os.environ.get("MAX_RESPONSE_MB", "500")),
            ),
        },
    )
    return rest.app


app = make_app()


def warm_up() -> None:
    """Open every store now, so the first client does not wait for all eight.

    The first catalog request opens them all (about 20 s for the CEFI stores).
    A store that fails here is logged and tried again on first request.
    """
    for dataset_id in STORES:
        try:
            open_store(dataset_id)
        except Exception:
            log.exception("could not open %s at startup", dataset_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    threading.Thread(target=warm_up, daemon=True).start()
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "9100")),
        # Behind Caddy the request arrives over plain HTTP from localhost;
        # trust its X-Forwarded-* headers so returned URLs use the public
        # https:// host.
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
