"""When a cached catalog is rebuilt (#3).

A catalog holds the datasets as they were when it was built, so a store that
gains time steps must not keep serving the old axis. Catalogs are keyed on the
data's ``_xpublish_id``, which Earthmover Flux changes with every commit, and
can also be given a maximum age.
"""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient
from xarray.backends import BackendArray
from xarray.core import indexing
from xpublish import Plugin, hookimpl

import xpublish_erddap.plugin as erddap_plugin
from xpublish_erddap import ErddapPlugin, formats
from xpublish_erddap.catalog import build_catalog

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


# --- one bad source must not take the server-wide root down (#56) ---------


class Flaky(Provider):
    """A provider whose ``broken`` datasets raise, or are listed but unknown."""

    broken: set = set()
    unlisted: list = []

    @hookimpl
    def get_datasets(self):
        return [*self.trees, *self.unlisted]

    @hookimpl
    def get_datatree(self, dataset_id: str, group: str):
        if dataset_id in self.broken:
            raise OSError("upstream store unreachable")
        return super().get_datatree(dataset_id, group)


def flaky_client(trees, **kwargs):
    provider = Flaky(trees=trees, **kwargs)
    rest = xpublish.Rest({}, plugins={"provider": provider, "erddap": ErddapPlugin()})
    return TestClient(rest.app)


def assert_good_served(client, caplog, bad):
    resp = client.get("/erddap/griddap/good.das")
    assert resp.status_code == 200, resp.text
    assert "good" in client.get("/erddap/griddap/index.csv").text
    assert bad in caplog.text


def test_dataset_that_raises_is_skipped(grid_dataset, caplog):
    client = flaky_client(
        {"good": version(grid_dataset, 2, "g"), "bad": version(grid_dataset, 2, "b")},
        broken={"bad"},
    )
    assert_good_served(client, caplog, "bad")
    assert client.get("/erddap/griddap/bad.das").status_code == 404
    # its own root still answers with an error for it alone
    assert client.get("/datasets/good/erddap/griddap/good.das").status_code == 200
    assert client.get("/datasets/bad/erddap/griddap/bad.das").status_code >= 400


def test_listed_but_unresolvable_id_is_skipped(grid_dataset, caplog):
    client = flaky_client({"good": version(grid_dataset, 2, "g")}, unlisted=["gone"])
    assert_good_served(client, caplog, "gone")


def test_noleap_dataset_beside_a_good_one(grid_dataset):
    # until #60 a noleap axis raised while building the catalog; now it is served
    cf = pytest.importorskip("cftime")
    del cf
    noleap = grid_dataset[["tos"]].isel(time=slice(0, 3))
    noleap = noleap.assign_coords(
        time=xr.date_range("2000-01-01", periods=3, calendar="noleap", use_cftime=True),
    )
    client = flaky_client(
        {"good": version(grid_dataset, 2, "g"), "cal": xr.DataTree(noleap)},
    )
    index = client.get("/erddap/griddap/index.csv").text
    assert "good" in index
    assert "cal" in index
    assert client.get("/erddap/griddap/cal.das").status_code == 200


def test_failed_source_returns_once_it_heals(grid_dataset):
    provider = Flaky(trees={"good": version(grid_dataset, 2, "g")}, unlisted=["late"])
    rest = xpublish.Rest({}, plugins={"provider": provider, "erddap": ErddapPlugin()})
    client = TestClient(rest.app)
    assert client.get("/erddap/griddap/late.das").status_code == 404
    provider.unlisted = []
    provider.trees["late"] = version(grid_dataset, 2, "l")
    assert client.get("/erddap/griddap/late.das").status_code == 200


# --- what the server-wide root opens, and when (#69) -------------------------


class Counting(Provider):
    """A provider that records every tree it is asked for."""

    opened: list = []

    @hookimpl
    def get_datatree(self, dataset_id: str, group: str):
        self.opened.append(dataset_id)
        return super().get_datatree(dataset_id, group)


@pytest.fixture
def counted(grid_dataset, monkeypatch):
    """A provider with three stores, a client, and a settable monotonic clock."""
    now = [1000.0]
    monkeypatch.setattr(erddap_plugin.time, "monotonic", lambda: now[0])

    def make(**kwargs):
        trees = {f"s{i}": version(grid_dataset, 2, f"s{i}@v1") for i in range(3)}
        provider = Counting(trees=trees, opened=[])
        rest = xpublish.Rest({}, plugins={"provider": provider, "erddap": ErddapPlugin(**kwargs)})
        return provider, TestClient(rest.app), now

    return make


LISTINGS = [
    "/erddap/griddap/index.csv",
    "/erddap/info/index.csv",
    "/erddap/search/index.csv?searchFor=all",
    "/erddap/search/advanced.csv?searchFor=all",
    "/erddap/categorize/institution/index.csv",
]


def opens(provider, client, url):
    provider.opened.clear()
    resp = client.get(url)
    assert resp.status_code == 200, resp.text
    return sorted(provider.opened)


def test_listings_reuse_the_catalog_between_checks(counted):
    provider, client, now = counted()
    assert opens(provider, client, LISTINGS[0]) == ["s0", "s1", "s2"]
    for url in LISTINGS:
        assert opens(provider, client, url) == [], url
    now[0] += 10  # catalog_check_s
    assert opens(provider, client, LISTINGS[0]) == ["s0", "s1", "s2"]


@pytest.mark.parametrize(
    "url",
    ["/erddap/griddap/s1.das", "/erddap/griddap/s1.csv?tos[0][0][0]", "/erddap/info/s1/index.csv"],
)
def test_one_dataset_opens_only_its_source(counted, url):
    provider, client, _ = counted()
    client.get(LISTINGS[0])
    assert opens(provider, client, url) == ["s1"]


def test_check_every_request_with_zero(counted):
    provider, client, _ = counted(catalog_check_s=0)
    client.get(LISTINGS[0])
    assert opens(provider, client, LISTINGS[0]) == ["s0", "s1", "s2"]


def with_depth(ds: xr.Dataset) -> xr.DataTree:
    """A commit to ``s0`` adding a variable on a new axis, so a new datasetID."""
    tree = ds[["tos", "thetao"]].isel(time=slice(0, 2))
    return xr.DataTree(tree.assign_attrs({"_xpublish_id": "s0@v2"}))


def test_a_new_commit_is_listed_after_the_check_interval(counted, grid_dataset):
    provider, client, now = counted()
    assert "s0_depth" not in client.get(LISTINGS[0]).text
    provider.trees["s0"] = with_depth(grid_dataset)
    # committed, but the check interval has not passed: still not listed
    assert "s0_depth" not in client.get(LISTINGS[0]).text
    now[0] += 10
    assert "s0_depth" in client.get(LISTINGS[0]).text


def test_unknown_id_checks_every_dataset_when_due(counted, grid_dataset):
    provider, client, now = counted()
    client.get(LISTINGS[0])
    provider.trees["s0"] = with_depth(grid_dataset)
    # not due: an id not in the catalog costs no opens
    provider.opened.clear()
    assert client.get("/erddap/griddap/s0_depth.das").status_code == 404
    assert provider.opened == []
    now[0] += 10
    assert client.get("/erddap/griddap/s0_depth.das").status_code == 200


def test_datasets_listed_or_dropped_show_at_once(counted, grid_dataset):
    provider, client, _ = counted()
    client.get(LISTINGS[0])
    provider.trees["s9"] = version(grid_dataset, 2, "s9@v1")
    del provider.trees["s1"]
    assert opens(provider, client, LISTINGS[0]) == ["s9"]
    index = client.get(LISTINGS[0]).text
    assert "s9" in index
    assert "s1" not in index
    assert client.get("/erddap/griddap/s1.das").status_code == 404


def test_concurrent_cold_requests_open_each_dataset_once(counted):
    provider, client, _ = counted()
    with ThreadPoolExecutor(4) as pool:
        codes = list(pool.map(lambda _: client.get(LISTINGS[0]).status_code, range(4)))
    assert codes == [200] * 4
    assert sorted(provider.opened) == ["s0", "s1", "s2"]


class CountingArray(BackendArray):
    """A lazy array, as a backend gives it, that counts reads of its values."""

    def __init__(self, values):
        self.values = values
        self.shape = values.shape
        self.dtype = values.dtype
        self.reads = 0

    def __getitem__(self, key):
        return indexing.explicit_indexing_adapter(
            key,
            self.shape,
            indexing.IndexingSupport.BASIC,
            self._read,
        )

    def _read(self, key):
        self.reads += 1
        return self.values[key]


def test_index_less_axes_are_read_once(grid_dataset):
    """``create_default_indexes=False`` leaves axes lazy; read them at build only."""
    lat = CountingArray(grid_dataset["lat"].values)
    source = grid_dataset[["tos"]].drop_vars("lat")
    source = source.assign_coords(
        xr.Coordinates({"lat": xr.Variable("lat", indexing.LazilyIndexedArray(lat))}, indexes={}),
    )
    assert "lat" not in source.indexes
    (entry,) = build_catalog("s", source)
    after_build = lat.reads
    for _ in range(3):  # what requests read
        entry.axes  # noqa: B018
        entry.variable_attrs("latitude")
        formats.das_response(entry, entry.ds)
    assert lat.reads == after_build
    # the host's dataset is left as it was
    assert not isinstance(source["lat"].variable._data, np.ndarray)


def test_cached_attributes_are_a_copy(grid_dataset):
    (entry,) = build_catalog("s", grid_dataset[["tos"]])
    entry.variable_attrs("tos")["units"] = "changed"
    assert entry.variable_attrs("tos")["units"] == "degC"
