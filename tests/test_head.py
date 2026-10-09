"""HEAD is answered like GET, without building a data file (#62)."""

import pytest
import xpublish
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin, formats


@pytest.fixture(scope="module")
def client(grid_dataset):
    rest = xpublish.Rest({"testgrid": grid_dataset}, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


@pytest.mark.parametrize(
    "path",
    [
        "/erddap/version",
        "/erddap/griddap/index.csv",
        "/erddap/info/index.json",
        "/erddap/info/testgrid/index.csv",
        "/erddap/search/index.csv?searchFor=testgrid",
        "/erddap/griddap/testgrid.das",
        "/erddap/griddap/testgrid.dds",
    ],
)
def test_head_matches_get(client, path):
    got = client.get(path)
    head = client.head(path)
    assert head.status_code == got.status_code == 200
    assert head.headers["content-type"] == got.headers["content-type"]
    assert head.content == b""


@pytest.mark.parametrize("ext", ["nc", "csv", "csvp", "csv0", "json"])
def test_head_on_data_builds_no_body(client, monkeypatch, ext):
    def boom(*args, **kwargs):
        raise AssertionError("a HEAD request built a data file")

    for name in ("to_netcdf_bytes", "to_erddap_json", "to_csv"):
        monkeypatch.setattr(formats, name, boom)
    head = client.head(f"/erddap/griddap/testgrid.{ext}")
    assert head.status_code == 200
    assert head.content == b""


def test_head_still_validates(client):
    assert client.head("/erddap/griddap/nope.csv").status_code == 404
    assert client.head("/erddap/griddap/testgrid.bogus").status_code == 400


def test_info_html_page(client):
    """rerddapXtracto's safe_info() and rerddap's browse() need this URL to exist."""
    for send in (client.get, client.head):
        resp = send("/erddap/info/testgrid/index.html")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
    page = client.get("/erddap/info/testgrid/index.html").text
    assert "/erddap/info/testgrid/index.csv" in page
    assert "/erddap/griddap/testgrid.dds" in page
    assert client.get("/erddap/info/nope/index.html").status_code == 404
