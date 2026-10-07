"""A stand-in for how Earthmover Flux routes a store's groups.

Flux serves each protocol as its own service, at
``.../{org}/{repo}/{ref}/{group path}/{protocol}`` (probed 2026-10-05). This
host does the same with xpublish's own machinery: dataset routers are mounted
below ``/{org}/{repo}/{ref}/{group_path:path}``, and the ``deps`` it hands
plugins resolve ``{org}/{repo}`` and the group. ``ref`` is accepted and
ignored. How Flux really does this is Earthmover's; the plugin relies only on
``deps``, so it should not matter.

A store's root group would need the path ``.../{ref}//erddap`` here, so only
groups below the root are reachable.
"""

from typing import Annotated

import xarray as xr
import xpublish
from fastapi import Depends
from xpublish.dependencies import get_group_path

#: Where ``tests/server.py`` mounts the host, as Flux's ERDDAP service would be.
FLUX_PREFIX = "/v1/services/erddap"


class FluxLikeRest(xpublish.Rest):
    """Datasets are ``{org}/{repo}``; routes are ``/{org}/{repo}/{ref}/{group}``."""

    def setup_datasets(self, datasets: dict) -> str:
        """Route dataset routers by org, repo, ref and group path."""
        super().setup_datasets(datasets)

        def datatree(
            org: str,
            repo: str,
            ref: str,  # noqa: ARG001
            group: Annotated[str, Depends(get_group_path)] = "",
        ) -> xr.DataTree:
            return self._resolve_datatree(f"{org}/{repo}", group)

        def dataset(
            org: str,
            repo: str,
            ref: str,
            group: Annotated[str, Depends(get_group_path)] = "",
        ) -> xr.Dataset:
            return datatree(org, repo, ref, group).dataset

        self._get_datatree_func = datatree
        self._get_dataset_func = dataset
        self._dataset_route_prefix = "/{org}/{repo}/{ref}/{group_path:path}"
        return self._dataset_route_prefix
