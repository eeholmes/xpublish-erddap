"""Save and rebuild a lazily opened ERDDAP dataset without its full data.

The reference datasets are tens of GB. A snapshot keeps what the parity
requests can see -- every axis, all metadata, and only the blocks of data the
requests read (plus a margin) -- in one small netCDF file. ``load_snapshot``
rebuilds a Dataset with the original shapes whose data variables are lazy and
raise if a read strays outside the captured blocks, so a wrong index shows up
as a loud error rather than as silently different values.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr
from xarray.backends import BackendArray
from xarray.core import indexing

#: Extra indices captured on each side of a requested block.
MARGIN = 2

_BLOCK = "__block"
_TEMPLATE_DIMS = "__dims"
_TEMPLATE_SHAPE = "__shape"

#: Attribute names the netCDF-4 library owns and will not let us write.
_RESERVED = {"_NCProperties", "_IsNetcdf4", "_SuperblockVersion", "_Format"}
_ESCAPE = "__escaped"


def _escape(attrs: dict) -> dict:
    return {(_ESCAPE + k if k in _RESERVED else k): v for k, v in attrs.items()}


def _unescape(attrs: dict) -> dict:
    return {
        (k.removeprefix(_ESCAPE) if k.removeprefix(_ESCAPE) in _RESERVED else k): v
        for k, v in attrs.items()
    }


def block_bounds(
    selections: dict[str, tuple[int, int]],
    sizes: dict[str, int],
) -> dict[str, tuple[int, int]]:
    """Widen inclusive ``(start, stop)`` index bounds by ``MARGIN``."""
    return {
        dim: (max(start - MARGIN, 0), min(stop + MARGIN, sizes[dim] - 1))
        for dim, (start, stop) in selections.items()
    }


def write_snapshot(
    ds: xr.Dataset,
    blocks: list[tuple[str, dict[str, tuple[int, int]]]],
    path: Path,
) -> None:
    """Write axes, metadata and the given data blocks of ``ds`` to ``path``.

    Args:
        ds: the lazily opened source dataset.
        blocks: ``(variable, {dim: (start, stop)})`` with inclusive bounds.
        path: the netCDF file to write.
    """
    out = xr.Dataset(coords={d: ds[d] for d in ds.dims}, attrs=_escape(ds.attrs))
    for name, da in ds.data_vars.items():
        template = xr.Variable((), np.zeros((), dtype=da.dtype), _escape(da.attrs))
        template.attrs[_TEMPLATE_DIMS] = " ".join(da.dims)
        template.attrs[_TEMPLATE_SHAPE] = np.asarray(da.shape, dtype="int64")
        template.encoding = _keep_encoding(da.encoding)
        out[name] = template
    for k, (name, bounds) in enumerate(blocks):
        da = ds[name]
        index = {d: slice(lo, hi + 1) for d, (lo, hi) in bounds.items()}
        values = da.isel(index).values
        dims = tuple(f"{_BLOCK}{k}_{d}" for d in da.dims)
        var = xr.Variable(dims, values)
        var.attrs["variable"] = name
        var.attrs["offsets"] = np.asarray(
            [bounds.get(d, (0, 0))[0] for d in da.dims],
            dtype="int64",
        )
        var.encoding = _keep_encoding(da.encoding)
        out[f"{_BLOCK}{k}"] = var
    out.to_netcdf(path, engine="netcdf4")


def _keep_encoding(encoding: dict) -> dict:
    keep = ("_FillValue", "missing_value", "dtype")
    return {k: v for k, v in encoding.items() if k in keep}


def load_snapshot(path: Path) -> xr.Dataset:
    """Rebuild the source dataset from a snapshot written by ``write_snapshot``."""
    snap = xr.open_dataset(path, engine="netcdf4")
    blocks: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
    for name in [n for n in snap.data_vars if str(n).startswith(_BLOCK)]:
        var = snap[name]
        blocks.setdefault(var.attrs["variable"], []).append(
            (np.asarray(var.attrs["offsets"]).reshape(-1), var.values),
        )
    out = xr.Dataset(coords={d: snap[d] for d in snap.dims if d in snap.coords})
    out.attrs = _unescape(snap.attrs)
    for name in snap.data_vars:
        if str(name).startswith(_BLOCK):
            continue
        template = snap[name]
        attrs = _unescape(template.attrs)
        dims = tuple(attrs.pop(_TEMPLATE_DIMS).split())
        shape = tuple(int(n) for n in np.asarray(attrs.pop(_TEMPLATE_SHAPE)).ravel())
        array = BlockArray(str(name), shape, template.dtype, blocks.get(name, []))
        var = xr.Variable(dims, indexing.LazilyIndexedArray(array), attrs)
        var.encoding = dict(template.encoding)
        out[name] = var
    return out


class NotCapturedError(KeyError):
    """A read touched data outside the snapshot's captured blocks."""


class BlockArray(BackendArray):
    """A full-size lazy array backed by a few captured blocks."""

    def __init__(self, name, shape, dtype, blocks):
        """Store the blocks; nothing is read until indexed."""
        self.name = name
        self.shape = shape
        self.dtype = np.dtype(dtype)
        self.blocks = blocks

    def __getitem__(self, key):
        """Index lazily, like a real backend."""
        return indexing.explicit_indexing_adapter(
            key,
            self.shape,
            indexing.IndexingSupport.BASIC,
            self._getitem,
        )

    def _getitem(self, key: tuple) -> np.ndarray:
        wanted = [np.arange(n)[k] for n, k in zip(self.shape, key, strict=True)]
        scalar_axes = tuple(i for i, w in enumerate(wanted) if np.ndim(w) == 0)
        wanted = [np.atleast_1d(w) for w in wanted]
        out = np.empty([len(w) for w in wanted], dtype=self.dtype)
        covered = np.zeros(out.shape, dtype=bool)
        for offsets, values in self.blocks:
            local, positions = [], []
            for w, off, n in zip(wanted, offsets, values.shape, strict=True):
                inside = (w >= off) & (w < off + n)
                positions.append(np.flatnonzero(inside))
                local.append(w[inside] - off)
            if any(p.size == 0 for p in positions):
                continue
            out[np.ix_(*positions)] = values[np.ix_(*local)]
            covered[np.ix_(*positions)] = True
        if not covered.all():
            msg = (
                f"{self.name}: read outside the captured blocks "
                f"(key {key}); add the request to cases.py and recapture"
            )
            raise NotCapturedError(msg)
        return out.squeeze(axis=scalar_axes) if scalar_axes else out
