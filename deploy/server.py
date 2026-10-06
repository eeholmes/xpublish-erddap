"""A Flux-like xpublish server: Icechunk stores behind OPeNDAP and ERDDAP.

Earthmover Flux serves Arraylake Icechunk stores with xpublish and the stock
xpublish-opendap plugin. This server does the same, adds xpublish-erddap beside
it, and serves two kinds of public Icechunk store:

- ``cefi_*``: five NOAA CEFI stores on Arraylake (``NOAA-PMEL/cefi-*``; see
  ``CEFI`` below). Virtual stores; their chunks are CEFI NetCDF files in
  NODD. The repos are public to any Arraylake account, so the server needs an
  Arraylake login or API token.
- ``gobai_o2_monthly``: plain Icechunk on S3 (Source Cooperative,
  ``fish-pace/gobai-o2/monthly``), read anonymously.
- ``hycom_gofs31``, ``ohc_*``, ``oisst``, ``oa_indicators``: EH's
  ``ocean-icechunks`` stores on Source Cooperative, read anonymously over
  HTTPS. These are published whole, as DataTrees: each group with variables
  is its own ERDDAP dataset (``ohc_na`` + ``daily`` is ``ohc_na_daily``).

Routes::

    /erddap/...                    one ERDDAP root listing every dataset
    /datasets/{id}/opendap.dds     stock xpublish-opendap, per dataset

Flux is one app too, but routes by store and group:
``.../{org}/{repo}/{ref}/{group path}/opendap``. ErddapPlugin cannot sit beside
each group yet (#18), so this server has a single ``/erddap`` root instead.
For a grouped store, ``/datasets/{id}/opendap`` shows only its (empty) root.
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


OCEAN_ICECHUNKS = "https://data.source.coop/ocean-icechunks"

_OHC_REGIONS = {"na": "North Atlantic", "np": "North Pacific", "sp": "South Pacific"}

#: EH's ocean-icechunks stores on Source Cooperative:
#: store id -> (path, ref, info page, {group: attributes to set}). The ref is
#: a tag when the store has a versioned one. Titles are set where the store's
#: own do not tell the groups apart (every OHC ``daily`` group is "Ocean Heat
#: Content Product Suite", ``14day*`` are ``OHC_NAQG3`` and so on) or are
#: missing (OISST ``monthly`` has no attributes at all), and summaries where
#: there is none, since search reads them. ``.`` is the root.
OCEAN_STORES: dict[str, tuple[str, dict, str, dict[str, dict[str, str]]]] = {
    "hycom_gofs31": (
        "hycom/hycom-gofs-3pt1-reanalysis",
        {"tag": "v1"},
        "https://source.coop/ocean-icechunks/hycom/docs/hycom-gofs-3pt1-reanalysis",
        {
            ".": {
                "summary": "HYCOM + NCODA global ocean reanalysis (GOFS 3.1, "
                "GLBv0.08 expt_53.X): temperature, salinity, currents and sea "
                "surface elevation at 1/12 degree on 40 depth levels, 3-hourly, "
                "1994-2015. A virtual Icechunk store over the NetCDF files in "
                "the HYCOM bucket on AWS Open Data.",
            },
        },
    ),
    **{
        f"ohc_{region}": (
            f"noaa-ohc/{region}",
            {"branch": "main"},
            "https://source.coop/ocean-icechunks/noaa-ohc",
            {
                "daily": {
                    "title": f"NOAA CoastWatch Ocean Heat Content, {name}, "
                    "Daily, 2020-04 to 2024-01",
                },
                "14day_v1": {
                    "title": f"NOAA CoastWatch Ocean Heat Content, {name}, "
                    "Daily (OHC14 product), 2024-01 to 2025-03",
                },
                "14day": {
                    "title": f"NOAA CoastWatch Ocean Heat Content, {name}, "
                    "Daily (OHC14 product), 2025-03 onward",
                },
            },
        )
        for region, name in _OHC_REGIONS.items()
    },
    "oisst": (
        "noaa-oisst/oisst.icechunk",
        {"branch": "main"},
        "https://source.coop/ocean-icechunks/noaa-oisst",
        {
            "monthly": {
                "title": "NOAA OISST v2.1 Sea Surface Temperature, Monthly "
                "Statistics of the Daily Fields",
                "summary": "Minimum, maximum, mean and standard deviation of "
                "NOAA's 1/4-degree Daily Optimum Interpolation SST v2.1 (sea "
                "surface temperature, its anomaly, analysis error and sea ice "
                "concentration) for every complete month since 1981-09, "
                "computed by NERACOOS/GMRI.",
                "institution": "NERACOOS / GMRI, from NOAA NCEI OISST v2.1",
            },
        },
    ),
    "oa_indicators": (
        "oa-indicators/climatology",
        {"branch": "main"},
        "https://source.coop/ocean-icechunks/oa-indicators",
        {},
    ),
}


def _open_ocean_icechunk(store_id: str) -> tuple[xr.DataTree, str]:
    path, ref, info_url, group_attrs = OCEAN_STORES[store_id]
    repo = icechunk.Repository.open(icechunk.http_storage(f"{OCEAN_ICECHUNKS}/{path}"))
    # The stores are virtual: their chunks are in other hosts' files, and each
    # host has to be authorized. All are public; OISST's are s3:// URLs.
    auth = icechunk.containers_credentials(
        {
            prefix: icechunk.s3_anonymous_credentials()
            if prefix.startswith("s3://")
            else icechunk.credentials.HttpAccess
            for prefix in repo.config.virtual_chunk_containers or {}
        }
    )
    session = repo.reopen(authorize_virtual_chunk_access=auth).readonly_session(**ref)
    tree = xr.open_datatree(session.store, engine="zarr", consolidated=False, chunks={})
    for node in tree.subtree:
        if not node.data_vars:
            continue
        node.attrs.setdefault("infoUrl", info_url)
        node.attrs.setdefault("cdm_data_type", "Grid")
        node.attrs.update(group_attrs.get(node.relative_to(tree), {}))
    return tree, session.snapshot_id


def _as_tree(opener: Callable[[], tuple[xr.Dataset, str]]) -> tuple[xr.DataTree, str]:
    ds, snapshot = opener()
    return xr.DataTree(dataset=ds), snapshot


#: Store id -> function that opens it lazily and returns (tree, snapshot).
#: A store whose variables are all at the root is a one-node tree, served
#: under the store id itself.
STORES: dict[str, Callable[[], tuple[xr.DataTree, str]]] = {
    **{
        dataset_id: partial(_as_tree, partial(_open_cefi, dataset_id))
        for dataset_id in CEFI
    },
    "gobai_o2_monthly": partial(_as_tree, _open_gobai),
    **{store_id: partial(_open_ocean_icechunk, store_id) for store_id in OCEAN_STORES},
}


@cache
def open_store(store_id: str) -> xr.DataTree:
    """Open a store once and keep it; record the snapshot it was pinned to."""
    tree, snapshot = STORES[store_id]()
    for node in tree.subtree:
        if node.data_vars:
            node.attrs["icechunk_snapshot"] = snapshot
    log.info("opened %s at snapshot %s", store_id, snapshot)
    return tree


class IcechunkProvider(Plugin):
    """Dataset provider plugin, the way Flux supplies datasets to xpublish."""

    name: str = "icechunk-provider"

    @hookimpl
    def get_datasets(self):
        """Ids of every store this server can open."""
        return list(STORES)

    @hookimpl
    def get_datatree(self, dataset_id: str, group: str):
        """Open the store on first use; ``None`` lets other providers try."""
        if dataset_id not in STORES:
            return None
        tree = open_store(dataset_id)
        return tree[group] if group else tree


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
    """Open every store now, so the first client does not wait for all of them.

    The first catalog request opens them all (about 20 s for the CEFI stores,
    a few more for the ocean-icechunks ones).
    A store that fails here is logged and tried again on first request.
    """
    for store_id in STORES:
        try:
            open_store(store_id)
        except Exception:
            log.exception("could not open %s at startup", store_id)


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
