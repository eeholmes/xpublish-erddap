"""How long the server-wide ``/erddap`` root takes with many datasets (#69).

Not a test (pytest does not collect it): run it by hand, in-process, with tiny
lazy datasets and a provider that takes ``--delay`` seconds to return a tree,
as a host that opens a store over the network would::

    python tests/benchmark_server_catalog.py              # N=200, 50 ms, reopening
    python tests/benchmark_server_catalog.py --n 1000 --cached

``--cached`` makes the provider keep the trees it opened (the delay is paid
once per store); without it every call reopens. Each line is the median of
``--repeat`` requests, after the first ("cold") request has built the catalog.
"""

from __future__ import annotations

import argparse
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import xarray as xr
import xpublish
from fastapi.testclient import TestClient
from xpublish import Plugin, hookimpl

from xpublish_erddap import ErddapPlugin


def store(i: int) -> xr.DataTree:
    """A small store, as a default open gives it (lazy, decoded)."""
    time_axis = pd.date_range("2020-01-01", periods=10, freq="D")
    ds = xr.Dataset(
        {
            "sst": (
                ("time", "lat", "lon"),
                np.zeros((10, 4, 5), "float32"),
                {"units": "degC", "long_name": f"Sea surface temperature {i}"},
            ),
        },
        coords={
            "time": time_axis,
            "lat": np.linspace(-10, 10, 4),
            "lon": np.linspace(100, 120, 5),
        },
        attrs={"title": f"Store {i}", "_xpublish_id": f"store{i}@v1"},
    )
    return xr.DataTree(ds.chunk())


class SlowProvider(Plugin):
    """A host whose stores take ``delay`` seconds to open."""

    name: str = "slow"
    n: int = 200
    delay: float = 0.05
    cached: bool = False
    opened: dict = {}
    calls: list = []

    @hookimpl
    def get_datasets(self):
        return [f"store{i}" for i in range(self.n)]

    @hookimpl
    def get_datatree(self, dataset_id: str, group: str):
        if not dataset_id.startswith("store"):
            return None
        self.calls.append(dataset_id)
        if self.cached and dataset_id in self.opened:
            return self.opened[dataset_id]
        time.sleep(self.delay)
        tree = store(int(dataset_id.removeprefix("store")))
        self.opened[dataset_id] = tree
        return tree


def timed(client: TestClient, url: str) -> float:
    start = time.perf_counter()
    resp = client.get(url)
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200, (url, resp.status_code, resp.text[:300])
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=200, help="number of stores")
    parser.add_argument("--delay", type=float, default=0.05, help="seconds to open a store")
    parser.add_argument("--cached", action="store_true", help="provider keeps opened stores")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--concurrent", type=int, default=60, help="slow requests in flight")
    args = parser.parse_args()

    provider = SlowProvider(n=args.n, delay=args.delay, cached=args.cached, opened={}, calls=[])
    rest = xpublish.Rest({}, plugins={"slow": provider, "erddap": ErddapPlugin()})
    client = TestClient(rest.app)
    mode = "cached" if args.cached else "reopening"
    print(f"N={args.n}, {args.delay * 1000:g} ms provider, {mode}")

    print(f"  cold  /erddap/griddap/index.csv         {timed(client, '/erddap/griddap/index.csv'):7.3f} s")
    last = f"store{args.n - 1}"
    urls = {
        "/erddap/griddap/index.csv": "/erddap/griddap/index.csv",
        "/erddap/search (searchFor=sst)": "/erddap/search/index.csv?searchFor=sst",
        "/erddap/search/advanced (minLat)": "/erddap/search/advanced.csv?minLat=0",
        f"/erddap/griddap/{last}.das": f"/erddap/griddap/{last}.das",
        f"/erddap/info/{last}/index.csv": f"/erddap/info/{last}/index.csv",
        f"/erddap/griddap/{last}.csv?sst[0][0][0]": f"/erddap/griddap/{last}.csv?sst[0][0][0]",
        f"per-dataset /datasets/{last}/erddap/griddap/{last}.das": (
            f"/datasets/{last}/erddap/griddap/{last}.das"
        ),
    }
    for label, url in urls.items():
        provider.calls.clear()
        times = [timed(client, url) for _ in range(args.repeat)]
        calls = len(provider.calls) / args.repeat
        print(f"  warm  {label:<40} {statistics.median(times):7.3f} s  ({calls:g} opens/request)")

    # /version while many slow requests hold the server's worker threads
    if args.concurrent:
        done = threading.Event()

        def slow() -> None:
            while not done.is_set():
                client.get(f"/erddap/griddap/{last}.das")

        with ThreadPoolExecutor(args.concurrent) as pool:
            for _ in range(args.concurrent):
                pool.submit(slow)
            time.sleep(1)
            version = timed(client, "/erddap/version")
            done.set()
        print(f"  /erddap/version with {args.concurrent} requests in flight  {version:7.3f} s")


if __name__ == "__main__":
    main()
