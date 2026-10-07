"""Check a running deploy/server.py the way users' client code would use it.

Usage::

    python deploy/check_clients.py http://127.0.0.1:9100
    python deploy/check_clients.py https://<host>

Runs erddapy (search, info, griddap subsets) against ``/erddap``. Every URL the
server hands back must start with the base URL given here; behind a proxy, that
shows the public host came through. When this machine can open the stores
itself (an Arraylake login is needed for CEFI), each subset is also compared
with a direct read of the store.

Prints one line per check with its time. ``KNOWN`` marks a failure that has an
open issue; it does not fail the run, and ``FIXED?`` says such a check now
passes. Exits non-zero if any other check failed.
"""

from __future__ import annotations

import re
import sys
import time
import traceback
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from erddapy import ERDDAP

#: dataset id -> (variable, ERDDAP constraints) for a small real subset.
SUBSETS = {
    "cefi_nep_hindcast_daily": (
        "tos",
        {
            "time>=": "2024-07-01T12:00:00Z",
            "time<=": "2024-07-03T12:00:00Z",
            "lat>=": 45.0,
            "lat<=": 46.0,
            "lon>=": 230.0,
            "lon<=": 231.0,
        },
    ),
    # A date-valued axis that is not called time, and an ensemble axis.
    "cefi_nwa_decadal_forecast_monthly_i196501": (
        "tos",
        {
            "member>=": 1,
            "member<=": 2,
            "lead>=": "1970-07-16T12:00:00Z",
            "lead<=": "1970-08-16T12:00:00Z",
            "lat>=": 40.0,
            "lat<=": 40.3,
            "lon>=": -68.0,
            "lon<=": -67.7,
        },
    ),
    "gobai_o2_monthly": (
        "oxy",
        {
            "time>=": "2020-01-15T00:00:00Z",
            "time<=": "2020-03-15T00:00:00Z",
            "pres>=": 10.0,
            "pres<=": 20.0,
            "lat>=": 0.0,
            "lat<=": 5.0,
            "lon>=": 180.0,
            "lon<=": 185.0,
        },
    ),
    # A group of a store published whole (real data, held in the store).
    "oisst_monthly": (
        "sst_mean",
        {
            "time>=": "2020-01-01T00:00:00Z",
            "time<=": "2020-03-01T00:00:00Z",
            "zlev>=": 0.0,
            "zlev<=": 0.0,
            "lat>=": 40.0,
            "lat<=": 41.0,
            "lon>=": 290.0,
            "lon<=": 291.0,
        },
    ),
}

#: ERDDAP datasetID -> (store id, group) where it is not a store's root.
GROUPS = {"oisst_monthly": ("oisst", "monthly")}

failures: list[str] = []


def check(name: str, known: str = ""):
    """Run the decorated function now as one named, timed check.

    ``known`` names the open issue for a failure we expect, so it is reported
    without failing the run.
    """

    def wrap(fn):
        t0 = time.perf_counter()
        try:
            note = fn() or ""
            status = "FIXED?" if known else "ok"
        except Exception as err:  # noqa: BLE001  (report every failure, keep going)
            note = f"{type(err).__name__}: {err}"
            if known:
                status, note = "KNOWN", f"{known}: {note}"
            else:
                status = "FAIL"
                failures.append(name)
                traceback.print_exc(file=sys.stderr)
        elapsed = time.perf_counter() - t0
        print(f"{status:6} {elapsed:6.2f}s  {name}  {note}"[:300], flush=True)
        return fn

    return wrap


def direct_opener():
    """Return deploy/server.py's ``open_store`` if the stores open here, else None."""
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from server import open_store  # noqa: PLC0415

        open_store("gobai_o2_monthly")
    except Exception as err:  # noqa: BLE001
        print(f"(no direct comparison: {type(err).__name__}: {err})", flush=True)
        return None
    return open_store


def subset(dataset_id: str, var: str, constraints: dict, response: str):
    """An erddapy client set up for one subset."""
    e = ERDDAP(server=ROOT, protocol="griddap", response=response)
    e.dataset_id = dataset_id
    e.griddap_initialize()
    e.constraints.update(constraints)
    e.variables = [var]
    return e


def main(base: str) -> int:  # noqa: C901
    """Run every check against ``base`` and return the exit code."""
    global ROOT  # noqa: PLW0603
    base = base.rstrip("/")
    ROOT = f"{base}/erddap"
    hostname = base.split("/")[2].split(":")[0]
    client = httpx.Client(timeout=120)
    open_store = direct_opener()

    @check("catalog lists every dataset checked here")
    def _():
        text = client.get(f"{ROOT}/info/index.csv").text
        missing = [d for d in SUBSETS if d not in text]
        assert not missing, f"missing {missing}"

    @check("erddapy search finds each dataset")
    def _():
        e = ERDDAP(server=ROOT, protocol="griddap")
        for term, dataset_id in [
            ("cefi", "cefi_nep_hindcast_daily"),
            ("oxygen", "gobai_o2_monthly"),
            ("heat", "ohc_na_daily"),
        ]:
            found = pd.read_csv(e.get_search_url(search_for=term, response="csv"))
            assert dataset_id in set(
                found["Dataset ID"],
            ), f"{term!r} -> {list(found['Dataset ID'])}"

    @check("erddapy search for 'all' lists everything")
    def _():
        e = ERDDAP(server=ROOT, protocol="griddap")
        found = pd.read_csv(e.get_search_url(search_for="all", response="csv"))
        assert set(SUBSETS) <= set(found["Dataset ID"])

    @check("every returned URL uses the base URL")
    def _():
        pages = [f"{ROOT}/info/index.csv", f"{ROOT}/search/index.json?searchFor=cefi"]
        for dataset_id in SUBSETS:
            pages += [
                f"{ROOT}/info/{dataset_id}/index.csv",
                f"{ROOT}/griddap/{dataset_id}.ncml",
            ]
        bad = set()
        for page in pages:
            for url in re.findall(r"https?://[^\s\"'<>,]+", client.get(page).text):
                # Only links back to this server matter, not infoUrl and the like.
                if url.split("/")[2].split(":")[0] == hostname and not url.startswith(
                    base,
                ):
                    bad.add(url)
        assert not bad, f"{len(bad)} URLs do not start with {base}: {sorted(bad)[:3]}"
        return f"{len(pages)} pages"

    @check(
        "stock xpublish-opendap honours a DAP stride",
        known="opendap-protocol bug, see #17",
    )
    def _():
        dds = client.get(
            f"{base}/datasets/gobai_o2_monthly/opendap.dds?lat[0:1:4]",
        ).text
        assert "lat = 5]" in dds, " ".join(dds.split())

    for dataset_id, (var, constraints) in SUBSETS.items():
        got = {}

        @check(f"{dataset_id}: erddapy to_xarray subset of {var}")
        def _(dataset_id=dataset_id, var=var, constraints=constraints, got=got):
            ds = subset(dataset_id, var, constraints, "nc").to_xarray()
            got["nc"] = ds[var].load()
            n_finite = int(np.isfinite(got["nc"]).sum())
            assert n_finite > 0, "every value is NaN"
            return f"shape {dict(ds[var].sizes)}, {n_finite} finite"

        @check(f"{dataset_id}: csv response matches nc")
        def _(dataset_id=dataset_id, var=var, constraints=constraints, got=got):
            df = subset(dataset_id, var, constraints, "csv").to_pandas()
            values = df[[c for c in df.columns if c.startswith(f"{var} ")][0]].to_numpy()
            np.testing.assert_allclose(
                values,
                got["nc"].values.ravel(),
                rtol=1e-6,
                equal_nan=True,
            )
            return f"{len(df)} rows"

        if open_store is not None:

            @check(f"{dataset_id}: subset matches a direct read of the store")
            def _(dataset_id=dataset_id, var=var, got=got):
                erd = got["nc"]
                store_id, group = GROUPS.get(dataset_id, (dataset_id, ""))
                tree = open_store(store_id)
                node = tree[group] if group else tree
                ref = node.to_dataset()[var].sel(
                    {d: erd[d].values for d in erd.dims},
                )
                np.testing.assert_allclose(
                    erd.values,
                    ref.transpose(*erd.dims).values,
                    equal_nan=True,
                )

    print(
        f"\n{len(failures)} unexpected failures" + (f": {failures}" if failures else ""),
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9100"))
