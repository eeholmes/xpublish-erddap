"""A Flux-like xpublish server: Icechunk stores behind OPeNDAP and ERDDAP.

Earthmover Flux serves Arraylake Icechunk stores with xpublish and the stock
xpublish-opendap plugin. This server does the same, adds xpublish-erddap beside
it, and serves two kinds of public Icechunk store:

- ``cefi_nep_hindcast_daily``: Arraylake (``NOAA-PMEL/cefi-nep-hindcast-daily``,
  group ``regrid/main``). A virtual store; its chunks are CEFI NetCDF files in
  NODD. The repo is public to any Arraylake account, so the server needs an
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

Stores are opened lazily on first request and pinned to the snapshot ``main``
pointed at then. New commits are not picked up until a restart (#3).

Run::

    python deploy/server.py                 # http://127.0.0.1:9100
    HOST=0.0.0.0 PORT=8000 python deploy/server.py

Data requests over ``MAX_RESPONSE_MB`` (default 500) get ERDDAP's 413.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from functools import cache

import icechunk
import uvicorn
import xarray as xr
import xpublish
from xpublish import Plugin, hookimpl
from xpublish_opendap import OpenDapPlugin

from xpublish_erddap import ErddapPlugin

log = logging.getLogger("flux_sim")


def _open_cefi() -> tuple[xr.Dataset, str]:
    from arraylake import Client  # noqa: PLC0415  (only this store needs it)

    repo = Client().get_repo("NOAA-PMEL/cefi-nep-hindcast-daily")
    session = repo.readonly_session("main")
    ds = xr.open_zarr(
        session.store,
        group="regrid/main",
        consolidated=False,
        chunks={},
    )
    # ACDD attributes ERDDAP clients expect and the store does not carry, the
    # counterpart of <addAttributes> in an ERDDAP datasets.xml.
    ds.attrs.update(
        {
            "title": "CEFI Northeast Pacific 10 km Hindcast, Daily, Regridded",
            "summary": (
                "NOAA CEFI MOM6-COBALT regional ocean hindcast for the Northeast "
                "Pacific, regridded to a regular grid. Served from a virtual "
                "Icechunk store on Arraylake."
            ),
            "institution": "NOAA CEFI",
            "infoUrl": "https://doi.org/10.5281/zenodo.13936240",
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
    "cefi_nep_hindcast_daily": _open_cefi,
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

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
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
