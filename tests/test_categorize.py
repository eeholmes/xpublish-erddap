"""``/erddap/categorize/`` (#5), ported from ERDDAP's ``Erddap.doCategorize``.

Expected texts are what erddap.ioos.us (2.31.1) and coastwatch.noaa.gov answered
on 2026-10-09: the attribute list in ``setup.xml`` order, values sorted and
already lower case, ``Not Found: (no details)`` for an unknown attribute or
value, a redirect from a value in the wrong case, and the dataset table at the
third level.
"""

import io

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import xpublish
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin
from xpublish_erddap.search import CATEGORY_ATTRIBUTES, DATASET_COLUMNS

erddapy = pytest.importorskip("erddapy")

SST_NAME = "sea_surface_temperature"
NOT_FOUND = 'Error {\n    code=404;\n    message="Not Found: (no details)";\n}\n'


def grid(title: str, institution: str | None = "NOAA NDBC", **attrs) -> xr.Dataset:
    lat, lon = np.arange(3.0), np.arange(4.0)
    sst = {"units": "degC", "standard_name": SST_NAME, "ioos_category": "Temperature"}
    ds = xr.Dataset(
        {"sst": (("lat", "lon"), np.zeros((3, 4)), sst)},
        coords={"lat": lat, "lon": lon},
        attrs={"title": title, "keywords": "Earth Science > Oceans, SST", **attrs},
    )
    if institution is not None:
        ds.attrs["institution"] = institution
    return ds


DATASETS = {
    "b": grid("Beta"),
    "a": grid("alpha", "Other Place", keywords="wind"),
    "c": grid("Gamma", None),
}


@pytest.fixture(scope="module")
def client():
    rest = xpublish.Rest(DATASETS, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


def table(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    return pd.read_csv(io.StringIO(resp.text), keep_default_na=False)


def test_attributes_are_erddaps_default_categories(client):
    got = table(client, "/erddap/categorize/index.csv")
    assert list(got.columns) == ["Categorize", "URL"]
    assert list(got["Categorize"]) == list(CATEGORY_ATTRIBUTES)
    assert list(got["Categorize"]) == [
        "cdm_data_type",
        "institution",
        "ioos_category",
        "keywords",
        "long_name",
        "standard_name",
        "variableName",
    ]
    assert got["URL"][1] == (
        "http://testserver/erddap/categorize/institution/index.csv?page=1&itemsPerPage=1000"
    )


def test_values_are_clean_sorted_and_link_to_their_datasets(client):
    got = table(client, "/erddap/categorize/institution/index.csv?page=1&itemsPerPage=7")
    assert list(got.columns) == ["Category", "URL"]
    # file-name safe, lower case, sorted; a dataset with none gets "unknown"
    assert list(got["Category"]) == ["noaa_ndbc", "other_place", "unknown"]
    assert got["URL"][0] == (
        "http://testserver/erddap/categorize/institution/noaa_ndbc/index.csv?page=1&itemsPerPage=7"
    )
    keywords = table(client, "/erddap/categorize/keywords/index.csv")
    assert list(keywords["Category"]) == ["oceans", "sst", "wind"]
    names = table(client, "/erddap/categorize/variableName/index.csv")
    assert list(names["Category"]) == ["latitude", "longitude", "sst"]
    standard = table(client, "/erddap/categorize/standard_name/index.csv")
    assert list(standard["Category"]) == ["_null", SST_NAME]
    ioos = table(client, "/erddap/categorize/ioos_category/index.csv")
    assert list(ioos["Category"]) == ["location", "temperature"]


def test_third_level_is_the_dataset_table_by_title(client):
    got = table(client, "/erddap/categorize/institution/noaa_ndbc/index.csv")
    assert list(got.columns) == DATASET_COLUMNS
    assert list(got["Dataset ID"]) == ["b"]
    got = table(client, "/erddap/categorize/ioos_category/temperature/index.csv")
    # by title, ignoring case: alpha, Beta, Gamma
    assert list(got["Dataset ID"]) == ["a", "b", "c"]
    assert got["Info"][0] == "http://testserver/erddap/info/a/index.csv"
    search = table(client, "/erddap/search/index.csv?searchFor=all")
    assert list(search.columns) == list(got.columns)


def test_third_level_pages(client):
    path = "/erddap/categorize/ioos_category/temperature/index.csv"
    assert list(table(client, f"{path}?page=2&itemsPerPage=2")["Dataset ID"]) == ["c"]
    resp = client.get(f"{path}?page=3&itemsPerPage=2")
    assert resp.status_code == 404
    assert "Your query produced no matching results. (nRows = 0)" in resp.text


def test_json(client):
    body = client.get("/erddap/categorize/keywords/index.json").json()["table"]
    assert body["columnNames"] == ["Category", "URL"]
    assert body["columnTypes"] == ["String", "String"]
    assert [row[0] for row in body["rows"]] == ["oceans", "sst", "wind"]
    got = client.get("/erddap/categorize/keywords/sst/index.json")
    assert got.headers["content-type"] == "application/json;charset=UTF-8"
    assert got.json()["table"]["columnNames"] == DATASET_COLUMNS


@pytest.mark.parametrize(
    "path",
    [
        "/erddap/categorize/foo/index.csv",
        "/erddap/categorize/foo/bar/index.csv",
        "/erddap/categorize/institution/nope/index.csv",
        "/erddap/categorize/Institution/noaa_ndbc/index.csv",
    ],
)
def test_unknown_attribute_or_value_is_erddaps_404(client, path):
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.text == NOT_FOUND


def test_value_in_the_wrong_case_redirects_to_lower_case(client):
    path = "/erddap/categorize/institution/NOAA_NDBC/index.csv"
    resp = client.get(f"{path}?itemsPerPage=5", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == (
        "http://testserver/erddap/categorize/institution/noaa_ndbc/index.csv?page=1&itemsPerPage=5"
    )
    # and a client that follows it gets the table
    assert list(table(client, path)["Dataset ID"]) == ["b"]


def test_html_is_refused_as_for_search(client):
    want = client.get("/erddap/search/index.html?searchFor=all")
    assert want.status_code == 404
    for path in (
        "categorize/index.html",
        "categorize/keywords/index.html",
        "categorize/keywords/sst/index.html",
    ):
        got = client.get(f"/erddap/{path}")
        assert got.status_code == 404
        assert got.text == want.text


def test_head_is_answered(client):
    for path in ("categorize/index.csv", "categorize/keywords/sst/index.csv"):
        assert client.head(f"/erddap/{path}").status_code == 200


def test_erddapy_get_categorize_url(client):
    """erddapy builds the URLs; each answers, and the links lead on."""
    e = erddapy.ERDDAP(server="http://testserver/erddap", protocol="griddap")

    url = e.get_categorize_url("institution", response="csv")
    assert url == "http://testserver/erddap/categorize/institution/index.csv"
    values = pd.read_csv(io.StringIO(client.get(url).text))
    assert "noaa_ndbc" in list(values["Category"])

    url = e.get_categorize_url("institution", "noaa_ndbc", response="csv")
    got = pd.read_csv(io.StringIO(client.get(url).text))
    assert list(got["Dataset ID"]) == ["b"]

    url = e.get_categorize_url("ioos_category", "temperature", response="json")
    rows = client.get(url).json()["table"]["rows"]
    assert len(rows) == len(DATASETS)

    # the URL column of one level is the next level's address
    link = values["URL"][values["Category"] == "noaa_ndbc"].iloc[0]
    assert client.get(link).status_code == 200


def test_per_dataset_root_categorizes_its_own_datasets(client):
    root = "/datasets/a/erddap"
    values = table(client, f"{root}/categorize/institution/index.csv")
    assert list(values["Category"]) == ["other_place"]
    got = table(client, f"{root}/categorize/institution/other_place/index.csv")
    assert list(got["Dataset ID"]) == ["a"]
    assert got["Info"][0] == "http://testserver/datasets/a/erddap/info/a/index.csv"
    assert client.get(f"{root}/categorize/institution/noaa_ndbc/index.csv").status_code == 404
    first = table(client, f"{root}/categorize/index.csv")["URL"][0]
    assert first.startswith("http://testserver/datasets/a/erddap/categorize/")


def test_erddapy_over_a_socket(xpublish_server):
    """The same against a running server (the tutorial dataset, #5)."""
    e = erddapy.ERDDAP(server=xpublish_server, protocol="griddap")
    values = pd.read_csv(e.get_categorize_url("cdm_data_type", response="csv"))
    assert "grid" in list(values["Category"])
    found = pd.read_csv(e.get_categorize_url("cdm_data_type", "grid", response="csv"))
    every = pd.read_csv(f"{xpublish_server}/griddap/index.csv")
    assert set(found["Dataset ID"]) == set(every["Dataset ID"])
