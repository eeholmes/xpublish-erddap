"""ERDDAP's dataset table and searches (#27, #4), beyond what the parity cases reach.

The parity cases check one real dataset (etopo5, one variable) against a real
server. These check the rules ported from ERDDAP's source that it does not
reach: the cut in the variable list, ranking, phrases, exclusions, paging,
keywords and ``now`` times.
"""

import io

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import xpublish
from fastapi import HTTPException
from fastapi.testclient import TestClient

from xpublish_erddap import ErddapPlugin
from xpublish_erddap.catalog import build_catalog
from xpublish_erddap.search import (
    DATASET_COLUMNS,
    advanced_filter,
    categories,
    extended_summary,
    no_long_lines_at_space,
    search_words,
    text_search,
)

#: The summary of ERDDAP's own allDatasets table, as erddap.ioos.us serves it
#: (2026-10-07): 105 characters, so it wraps to two lines.
ALL_DATASETS_SUMMARY = (
    "This dataset is a table which has a row of information for each dataset "
    "currently active in this ERDDAP."
)


def grid(n_vars: int = 1, summary: str = "A summary.", **attrs) -> xr.Dataset:
    lat, lon = np.arange(3.0), np.arange(4.0)
    data = {f"v{i:02d}": (("lat", "lon"), np.zeros((3, 4)), {"units": "m"}) for i in range(n_vars)}
    return xr.Dataset(
        data,
        coords={"lat": lat, "lon": lon},
        attrs={"title": "T", "summary": summary, **attrs},
    )


def entry(ds: xr.Dataset, dataset_id: str = "d"):
    return build_catalog(dataset_id, ds)[0]


def test_variable_list_is_cut_as_erddap_cuts_it():
    """allDatasets has 36 variables; ERDDAP lists 26 and '... (10 more variables)'."""
    summary = extended_summary(entry(grid(36, ALL_DATASETS_SUMMARY)))
    listed = [line for line in summary.splitlines() if line.startswith("v")]
    assert len(listed) == 26
    assert summary.endswith("... (10 more variables)\n")


def test_a_few_more_variables_are_not_cut():
    """ERDDAP does not cut when only a few would remain."""
    summary = extended_summary(entry(grid(30)))
    assert "more variables" not in summary


def test_variable_detail_follows_erddap():
    ds = grid(1)
    ds["v00"].attrs = {"long_name": "Sea Height", "units": "m"}
    ds["sst"] = ds["v00"].assign_attrs(long_name="SST", units="")  # same length
    summary = extended_summary(entry(ds))
    assert "v00 (Sea Height, m)\n" in summary
    assert "sst\n" in summary
    assert (
        "cdm_data_type = Grid\nVARIABLES (all of which use the dimensions [latitude][longitude]):"
        in summary
    )


def test_long_lines_wrap_at_spaces_as_erddap():
    assert no_long_lines_at_space(ALL_DATASETS_SUMMARY).count("\n") == 1
    assert no_long_lines_at_space("short") == "short"


def test_search_words():
    assert search_words('sea "surface temp" -wind, ice') == [
        (False, "sea"),
        (False, "surface temp"),
        (True, "wind"),
        (False, "ice"),
    ]


def test_text_search_ranks_by_position_then_title():
    early = entry(grid().assign_attrs(title="Ocean Wind"), "b")
    late = entry(grid().assign_attrs(title="Zeta", comment="ocean wind"), "a")
    assert [d.dataset_id for d in text_search([late, early], "wind")] == ["b", "a"]
    assert [d.dataset_id for d in text_search([late, early], "wind -zeta")] == ["b"]
    assert text_search([late, early], '"wind ocean"') == []


def test_keywords_split_and_clean_as_erddap():
    ds = grid(keywords="Earth Science > Oceans > Ocean Temperature, SST")
    cats = categories(entry(ds))
    # ">" and spaces are not file-name safe: each becomes "_", runs collapse
    assert cats["keywords"] == {"oceans_ocean_temperature", "sst"}


def test_now_times_and_bad_times():
    d = entry(grid().expand_dims(time=pd.to_datetime(["2000-01-01"])))
    assert advanced_filter([d], {"minTime": "now-30years"}) == [d]
    assert advanced_filter([d], {"minTime": "now-1day"}) == []
    with pytest.raises(HTTPException) as err:
        advanced_filter([d], {"minTime": "yesterday"})
    assert err.value.status_code == 400


@pytest.fixture(scope="module")
def client():
    datasets = {f"d{i}": grid(title=f"Grid {i}") for i in range(5)}
    rest = xpublish.Rest(datasets, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


def table(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    return pd.read_csv(io.StringIO(resp.text))


def test_tabledap_index_has_erddaps_columns(client):
    """The griddap, info and search tables are parity cases (etopo5 c00, c13-c15)."""
    resp = client.get("/erddap/tabledap/index.json")
    assert resp.json()["table"]["columnNames"] == DATASET_COLUMNS


def test_paging(client):
    page = table(client, "/erddap/griddap/index.csv?page=2&itemsPerPage=2")
    assert list(page["Dataset ID"]) == ["d2", "d3"]
    resp = client.get("/erddap/search/index.csv?searchFor=grid&page=9&itemsPerPage=2")
    assert resp.status_code == 404
