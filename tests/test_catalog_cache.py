"""When a cached catalog is rebuilt (#3).

A catalog holds the datasets as they were when it was built, so a store that
gains time steps must not keep serving the old axis. Catalogs are keyed on the
data's ``_xpublish_id``, which Earthmover Flux changes with every commit, and
can also be given a maximum age.
"""

import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient
from xpublish import Plugin, hookimpl

import xpublish_erddap.plugin as erddap_plugin
from xpublish_erddap import ErddapPlugin

ROOTS = ["/erddap", "/datasets/store/erddap"]


class Provider(Plugin):
    """Serves whatever tree is in ``trees`` now, as a host serving a live store."""

    name: str = "provider"
    trees: dict = {}

    @hookimpl
    def get_datasets(self):
        return list(self.trees)

    @hookimpl
    def get_datatree(self, dataset_id: str, group: str):
        if dataset_id not in self.trees:
            return None
        tree = self.trees[dataset_id]
        return tree[group] if group else tree


def version(ds: xr.Dataset, n_times: int, xpublish_id: str) -> xr.DataTree:
    """The store with its first ``n_times`` time steps, tagged ``xpublish_id``."""
    first = ds[["tos"]].isel(time=slice(0, n_times))
    return xr.DataTree(first.assign_attrs({"_xpublish_id": xpublish_id}))


def last_time(client: TestClient, root: str) -> str:
    resp = client.get(f"{root}/griddap/store.csv?time[last]")
    assert resp.status_code == 200, resp.text
    return resp.text.splitlines()[2]


@pytest.fixture
def served(grid_dataset):
    """A provider, a client for an app built with ``plugin``, and the dataset."""

    def make(plugin: ErddapPlugin):
        provider = Provider(trees={"store": version(grid_dataset, 2, "store@v1")})
        rest = xpublish.Rest({}, plugins={"provider": provider, "erddap": plugin})
        return provider, TestClient(rest.app)

    return make


@pytest.mark.parametrize("root", ROOTS)
def test_new_xpublish_id_rebuilds_the_catalog(served, grid_dataset, root):
    """A commit (new snapshot, so new _xpublish_id) shows up on the next request."""
    provider, client = served(ErddapPlugin())
    before = last_time(client, root)
    provider.trees["store"] = version(grid_dataset, 3, "store@v2")
    assert last_time(client, root) > before


@pytest.mark.parametrize("root", ROOTS)
def test_same_xpublish_id_keeps_the_catalog(served, grid_dataset, root):
    """Without a new id or a maximum age, the catalog is kept (documented)."""
    provider, client = served(ErddapPlugin())
    before = last_time(client, root)
    provider.trees["store"] = version(grid_dataset, 3, "store@v1")
    assert last_time(client, root) == before


@pytest.mark.parametrize("root", ROOTS)
def test_max_age_rebuilds_under_the_same_id(served, grid_dataset, root, monkeypatch):
    """catalog_max_age_s covers data that changes in place under a fixed id."""
    now = [1_000_000.0]
    monkeypatch.setattr(erddap_plugin.time, "time", lambda: now[0])
    provider, client = served(ErddapPlugin(catalog_max_age_s=60))
    before = last_time(client, root)
    provider.trees["store"] = version(grid_dataset, 3, "store@v1")
    assert last_time(client, root) == before
    now[0] += 61
    assert last_time(client, root) > before
