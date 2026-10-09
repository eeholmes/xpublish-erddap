"""OPeNDAP binary (``.dods``) responses, decoded here by DAP2's rules (#2).

The parity tests compare whole responses with real ERDDAP servers byte for
byte; these check what those datasets do not have (unsigned, 16- and 64-bit
integers, masked fills, a whole-dataset request) and the encoding itself.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import xpublish
from error_body import message
from fastapi.testclient import TestClient

import xpublish_erddap.formats as formats_module
import xpublish_erddap.plugin as plugin_module
from xpublish_erddap import ErddapPlugin

#: How DAP2 sends each DDS type (XDR has no 8- or 16-bit numbers).
XDR = {
    "Byte": "u1",
    "Int16": ">i4",
    "UInt16": ">u4",
    "Int32": ">i4",
    "UInt32": ">u4",
    "Float32": ">f4",
    "Float64": ">f8",
}


def decode(body: bytes) -> tuple[str, list[tuple[str, np.ndarray]]]:
    """A .dods body as its DDS and each array in order, maps included."""
    dds, sep, data = body.partition(b"\nData:\n")
    assert sep, "no Data: separator"
    dds = dds.decode("latin-1")
    arrays = []
    po = 0
    # every array declaration in DDS order: ARRAY then MAPS for a grid
    for kind, name in re.findall(r"^\s*(\w+) (\w+)\[", dds, flags=re.MULTILINE):
        n, again = np.frombuffer(data, ">i4", 2, po)
        assert n == again, "a DAP2 length is sent twice"
        po += 8
        dtype = np.dtype(XDR[kind])
        arrays.append((name, np.frombuffer(data, dtype, n, po)))
        po += n * dtype.itemsize
        po += -po % 4  # bytes are padded to 4
    assert po == len(data), f"{len(data) - po} bytes left over"
    return dds, arrays


@pytest.fixture(scope="module")
def client(grid_dataset):
    rest = xpublish.Rest({"testgrid": grid_dataset}, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


def epoch(times) -> np.ndarray:
    return (np.asarray(times) - np.datetime64(0, "s")) / np.timedelta64(1, "s")


def test_grid_request_sends_array_then_maps(client, grid_dataset):
    query = "tos[1:1:2][0:2:4][3]"
    resp = client.get(f"/erddap/griddap/testgrid.dods?{query}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream;charset=ISO-8859-1"
    assert "content-disposition" not in resp.headers
    dds, arrays = decode(resp.content)
    assert dds == client.get(f"/erddap/griddap/testgrid.dds?{query}").text
    sub = grid_dataset.isel(time=slice(1, 3), lat=slice(0, 5, 2), lon=slice(3, 4))
    assert [name for name, _ in arrays] == ["tos", "time", "latitude", "longitude"]
    np.testing.assert_array_equal(arrays[0][1], sub.tos.values.ravel())
    np.testing.assert_array_equal(arrays[1][1], epoch(sub.time.values))
    np.testing.assert_array_equal(arrays[2][1], sub.lat.values)
    np.testing.assert_array_equal(arrays[3][1], sub.lon.values)


def test_axis_request_sends_only_those_axes(client, grid_dataset):
    _, arrays = decode(client.get("/erddap/griddap/testgrid.dods?longitude,time[(last)]").content)
    assert [name for name, _ in arrays] == ["time", "longitude"]  # dataset order, as the DDS
    np.testing.assert_array_equal(arrays[0][1], epoch(grid_dataset.time.values[-1:]))


def test_whole_dataset_sends_every_axis_first(client):
    _, arrays = decode(client.get("/erddap/griddap/testgrid.dods").content)
    names = [name for name, _ in arrays]
    assert names[:3] == ["time", "latitude", "longitude"]
    assert names[3:] == [
        "tos",
        "time",
        "latitude",
        "longitude",
        "sos",
        "time",
        "latitude",
        "longitude",
    ]


def test_grid_member_names_as_netcdf_c_sends_them(client, grid_dataset):
    """netCDF-C asks for ``tos.tos[...]``; ``tos.latitude`` names an axis (EDDGrid)."""
    plain = client.get("/erddap/griddap/testgrid.dods?tos[0][0][0]").content
    assert client.get("/erddap/griddap/testgrid.dods?tos.tos%5b0%5d%5b0%5d%5b0%5d").content == (
        plain
    )
    _, arrays = decode(client.get("/erddap/griddap/testgrid.dods?tos.latitude[0:1:1]").content)
    assert [name for name, _ in arrays] == ["latitude"]
    np.testing.assert_array_equal(arrays[0][1], grid_dataset.lat.values[:2])


@pytest.fixture(scope="module")
def typed_client() -> TestClient:
    """Every integer width, and fills that xarray masks into NaN."""
    shape = (1, 3, 3)  # 9 cells: an odd count, so bytes need padding
    dims = ("time", "lat", "lon")
    cells = np.arange(9).reshape(shape)
    raw = xr.Dataset(
        {
            "b": (dims, (cells - 4).astype("int8")),
            "ub": (dims, (cells + 250).astype("uint8")),
            "s": (dims, (cells * -1000).astype("int16")),
            "us": (dims, (cells + 65000).astype("uint16")),
            "i": (dims, (cells * 100000).astype("int32")),
            "big": (dims, (cells + 2**40).astype("int64")),
            # stored Int16 with a fill, as xarray decodes it: float32 with NaN
            "masked": (
                dims,
                np.where(cells == 4, -999, cells).astype("int16"),
                {"_FillValue": -999},
            ),
            "f": (dims, np.where(cells == 0, -9.0, cells).astype("float32"), {"_FillValue": -9.0}),
        },
        coords={
            "time": pd.to_datetime(["2020-01-01"]),
            "lat": [1.0, 2.0, 3.0],
            "lon": np.array([10, 20, 30], dtype="int16"),
        },
    )
    ds = xr.decode_cf(raw)
    assert ds.masked.dtype.kind == "f" and np.isnan(ds.f.values.flat[0])
    rest = xpublish.Rest({"typed": ds}, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


@pytest.mark.parametrize(
    ("name", "kind", "expected"),
    [
        ("b", "Byte", (np.arange(9) - 4).astype("int8").view("uint8")),
        ("ub", "Byte", (np.arange(9) + 250).astype("uint8")),
        ("s", "Int16", np.arange(9) * -1000),
        ("us", "UInt16", np.arange(9) + 65000),
        ("i", "Int32", np.arange(9) * 100000),
        ("big", "Float64", (np.arange(9) + 2**40).astype("float64")),
        # the fill goes back in: ERDDAP's .dods is not converted to NaN
        ("masked", "Int16", np.where(np.arange(9) == 4, -999, np.arange(9))),
        ("f", "Float32", np.where(np.arange(9) == 0, -9.0, np.arange(9))),
    ],
)
def test_types_and_fills(typed_client, name, kind, expected):
    resp = typed_client.get(f"/erddap/griddap/typed.dods?{name}[0][0:1:2][0:1:2]")
    dds, arrays = decode(resp.content)
    assert f"{kind} {name}[" in dds
    np.testing.assert_array_equal(arrays[0][1], expected)
    # the Int16 lon axis is a 32-bit int too
    np.testing.assert_array_equal(arrays[-1][1], [10, 20, 30])


def test_blocks_stream_the_same_bytes(client, monkeypatch):
    """A response read a few cells at a time is the same response."""
    whole = client.get("/erddap/griddap/testgrid.dods?tos,sos").content
    monkeypatch.setattr(formats_module, "DODS_BLOCK_BYTES", 20)
    assert client.get("/erddap/griddap/testgrid.dods?tos,sos").content == whole


def test_array_too_long_for_dap2(client, monkeypatch):
    """ERDDAP's 'OPeNDAP limit': a DAP2 length is a 32-bit int."""
    monkeypatch.setattr(plugin_module, "DAP_ARRAY_LIMIT", 120)
    resp = client.get("/erddap/griddap/testgrid.dods?tos")
    assert resp.status_code == 413
    assert message(resp).endswith(
        "The request needs an array size (120) bigger than Java ever allows (120). "
        "[memory] (OPeNDAP limit)",
    )
    # an axis is never refused, and nor is a smaller grid request
    assert client.get("/erddap/griddap/testgrid.dods?time").status_code == 200
    assert client.get("/erddap/griddap/testgrid.dods?tos[0:1:4][][]").status_code == 200


def test_grid_member_names_need_a_real_grid(client):
    """``EDDGrid.parseAxisDapQuery`` refuses an unknown grid before the dot."""
    resp = client.get("/erddap/griddap/testgrid.dods?nope.latitude")
    assert resp.status_code == 400
    assert "nope" in message(resp)
    # a data variable's other members are not shortened: tos.sos is unknown
    assert client.get("/erddap/griddap/testgrid.dods?tos.sos[0][0][0]").status_code == 400
