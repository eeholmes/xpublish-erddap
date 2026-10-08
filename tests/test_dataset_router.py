"""The per-dataset ERDDAP root (#18): one root per dataset, or per group.

Flux serves each group of a store at ``.../{org}/{repo}/{ref}/{group}`` and
puts each protocol beside it (``.../opendap``), so ERDDAP has to work there
too, not only as one server-wide ``/erddap``.
"""

import io
import sys

import pandas as pd
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient
from flux_host import FLUX_PREFIX, FluxLikeRest

from xpublish_erddap import ErddapPlugin

TOS = "tos[0][0][0]"


def ids(client: TestClient, root: str) -> list[str]:
    body = client.get(f"{root}/griddap/index.csv").text
    return sorted(pd.read_csv(io.StringIO(body))["Dataset ID"])


@pytest.fixture(scope="module")
def tos_only(grid_dataset):
    return grid_dataset[["tos"]]


def test_rest_has_a_root_per_dataset(grid_dataset):
    """Each dataset's root lists that dataset only; /erddap still lists all."""
    rest = xpublish.Rest(
        {"a": grid_dataset, "b": grid_dataset},
        plugins={"erddap": ErddapPlugin()},
    )
    client = TestClient(rest.app)
    assert ids(client, "/datasets/a/erddap") == ["a", "a_depth"]
    assert ids(client, "/erddap") == ["a", "a_depth", "b", "b_depth"]

    body = client.get("/datasets/a/erddap/info/index.csv").text
    assert "http://testserver/datasets/a/erddap/griddap/a," in body
    assert "http://testserver/datasets/a/erddap/info/a_depth/index.csv" in body
    resp = client.get(f"/datasets/a/erddap/griddap/a.csv?{TOS}")
    assert resp.status_code == 200
    assert client.get("/datasets/a/erddap/info/b/index.csv").status_code == 404


def test_single_dataset_rest_serves_its_dataset(grid_dataset):
    """Under SingleDatasetRest the per-dataset root is /erddap (#18's first symptom)."""
    rest = xpublish.SingleDatasetRest(grid_dataset, plugins={"erddap": ErddapPlugin()})
    client = TestClient(rest.app)
    assert ids(client, "/erddap") == ["dataset", "dataset_depth"]
    assert client.get("/erddap/info/dataset/index.csv").status_code == 200
    assert client.get(f"/erddap/griddap/dataset.csv?{TOS}").status_code == 200


def test_dataset_naming_is_configurable(grid_dataset):
    """A host can name datasets its own way (docs/hosting.md)."""
    plugin = ErddapPlugin(name_dataset=lambda params, group: "sst_analysis")
    client = TestClient(
        xpublish.SingleDatasetRest(grid_dataset, plugins={"erddap": plugin}).app,
    )
    assert ids(client, "/erddap") == ["sst_analysis", "sst_analysis_depth"]


@pytest.fixture(scope="module")
def flux_client(tos_only):
    tree = xr.DataTree.from_dict({"/regrid/main": tos_only, "/raw": tos_only})
    host = FluxLikeRest(
        {"NOAA-PMEL/cefi-store": tree},
        plugins={"erddap": ErddapPlugin()},
    )
    return TestClient(host.app)


def test_flux_like_host_has_a_root_per_group(flux_client):
    """Each group's root lists only that group, named org/repo/ref + group."""
    regrid = "/NOAA-PMEL/cefi-store/main/regrid/main/erddap"
    raw = "/NOAA-PMEL/cefi-store/main/raw/erddap"
    # In this order, a catalog cached under one key would answer for both.
    assert ids(flux_client, regrid) == ["NOAA_PMEL_cefi_store_main_regrid_main"]
    assert ids(flux_client, raw) == ["NOAA_PMEL_cefi_store_main_raw"]

    body = flux_client.get(f"{raw}/info/index.csv").text
    assert f"http://testserver{raw}/griddap/NOAA_PMEL_cefi_store_main_raw," in body
    resp = flux_client.get(f"{raw}/griddap/NOAA_PMEL_cefi_store_main_raw.csv?{TOS}")
    assert resp.status_code == 200


def test_flux_like_host_has_no_server_wide_root(flux_client):
    """It cannot be asked for a dataset by one id, so /erddap stays out."""
    assert flux_client.get("/erddap/version").status_code == 404


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Live server tests are unreliable on Windows Github Actions workers",
)
def test_erddapy_against_a_flux_like_group_root(xpublish_server):
    """Plain erddapy code against one group's root, as a Flux user would."""
    erddapy = pytest.importorskip("erddapy")
    root = xpublish_server.replace(
        "/erddap",
        f"{FLUX_PREFIX}/NOAA-PMEL/cefi-nep-hindcast-daily/main/regrid/main/erddap",
    )
    dataset_id = "NOAA_PMEL_cefi_nep_hindcast_daily_main_regrid_main"
    found = pd.read_csv(f"{root}/search/index.csv?searchFor=all")
    assert dataset_id in set(found["Dataset ID"])

    e = erddapy.ERDDAP(server=root, protocol="griddap", response="nc")
    e.dataset_id = dataset_id
    e.griddap_initialize()
    assert e.variables == ["tos"]
    ds = e.to_xarray()
    assert ds["tos"].size > 0


def test_flux_like_host_can_drop_org_and_ref(tos_only):
    """The likeliest change for Flux: name by repo and group only."""

    def by_repo(params: dict[str, str], group: str) -> str:
        return f"{params['repo']}/{group}" if group else params["repo"]

    tree = xr.DataTree.from_dict({"/regrid/main": tos_only})
    host = FluxLikeRest(
        {"NOAA-PMEL/cefi-store": tree},
        plugins={"erddap": ErddapPlugin(name_dataset=by_repo)},
    )
    client = TestClient(host.app)
    assert ids(client, "/NOAA-PMEL/cefi-store/main/regrid/main/erddap") == [
        "cefi_store_regrid_main",
    ]


def group_blind_client(tos_only, **plugin_args):
    """Two groups with different variables, under a name that ignores the group."""
    tree = xr.DataTree.from_dict(
        {
            "/regrid": tos_only,
            "/raw": tos_only.rename({"tos": "chl"}),
        },
    )
    plugin = ErddapPlugin(
        name_dataset=lambda params, group: params["repo"],
        **plugin_args,
    )
    host = FluxLikeRest({"org/store": tree}, plugins={"erddap": plugin})
    return TestClient(host.app)


def test_groups_with_one_name_each_serve_their_own_catalog(tos_only):
    """Caches follow the URL, not name_dataset: /regrid must not answer for /raw (#61)."""
    client = group_blind_client(tos_only)
    for group, variable in [("regrid", "tos"), ("raw", "chl"), ("regrid", "tos")]:
        root = f"/org/store/main/{group}/erddap"
        resp = client.get(f"{root}/griddap/store.das")
        assert resp.status_code == 200, resp.text
        assert variable in resp.text


def test_alternating_refs_do_not_rebuild_every_request(tos_only, monkeypatch):
    """A name that drops the ref must not make refs evict each other (#61)."""
    builds = []
    original = ErddapPlugin.build

    def counting(self, source_id, tree):
        builds.append(source_id)
        return original(self, source_id, tree)

    monkeypatch.setattr(ErddapPlugin, "build", counting)
    client = group_blind_client(tos_only)
    for ref in ["main", "v1"] * 3:
        assert client.get(f"/org/store/{ref}/regrid/erddap/griddap/store.das").status_code == 200
    assert len(builds) == 2


def test_cache_is_told_the_catalog_size(tos_only):
    """cachey counts an unsized tuple as ~56 B; give it a real estimate (#61)."""
    tree = xr.DataTree.from_dict({"/regrid": tos_only})
    host = FluxLikeRest({"org/store": tree}, plugins={"erddap": ErddapPlugin()})
    client = TestClient(host.app)
    assert (
        client.get("/org/store/main/regrid/erddap/griddap/org_store_main_regrid.das").status_code
        == 200
    )
    assert host.cache.total_bytes > 10 * 56 * len(host.cache.data)
