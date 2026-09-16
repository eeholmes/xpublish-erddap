"""Map xarray Datasets onto ERDDAP griddap datasets.

ERDDAP's EDDGrid model requires every data variable in a dataset to share
*all* of the dataset's axis variables. An xarray Dataset (or a Zarr/Icechunk
group) has no such rule, so one source dataset may map to several ERDDAP
datasets -- one per distinct dimension signature.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import xarray as xr

__all__ = [
    "AxisProblem",
    "coverage_globals",
    "nice_doubles",
    "ErddapDataset",
    "REQUIRED_GLOBALS",
    "build_catalog",
    "check_axes",
    "sanitize_id",
]

logger = logging.getLogger("uvicorn")

#: An axis needs at least two values before monotonicity means anything.
_MIN_AXIS_LEN = 2

#: Global attributes ERDDAP requires on every dataset.
REQUIRED_GLOBALS = (
    "title",
    "summary",
    "institution",
    "infoUrl",
    "license",
    "Conventions",
    "cdm_data_type",
)

_FALLBACK_GLOBALS = {
    "summary": "No summary supplied. Set `summary` in the dataset metadata.",
    "institution": "unknown",
    "infoUrl": "???",
    "license": "[standard]",
    "Conventions": "CF-1.10, COARDS, ACDD-1.3",
    "cdm_data_type": "Grid",
}

# Rough CF/unit heuristics for ioos_category, which ERDDAP requires per variable.
_IOOS_BY_NAME = (
    (r"temp|sst|tos|tob|thetao", "Temperature"),
    (r"salin|\bsos\b|\bsob\b|\bso\b|sfdsi|salt", "Salinity"),
    (r"chl|phyto|zoo|nitrate|no3|po4|silicate|oxygen|o2|ph\b|co3|alk", "Biology"),
    (r"\bu\b|\bv\b|siu|siv|current|speed|_vel|velocity|umo|vmo", "Currents"),
    (r"ssh|zos|sea_surface_height|pbo", "Sea Level"),
    (r"ice|sic|sit|snow", "Ice Distribution"),
    (r"wind|tau", "Wind"),
    (r"heat|hf|rad|rls|rss|flux", "Heat Flux"),
    (r"\bpr\b|prlq|prsn|rain|evap|wfo|runoff|friver", "Hydrology"),
    (r"mld|mlotst", "Physical Oceanography"),
)


def sanitize_id(text: str) -> str:
    """Coerce ``text`` into a legal ERDDAP datasetID (``[A-Za-z][A-Za-z0-9_]*``)."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", text)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"d_{cleaned}"
    return cleaned


def infer_ioos_category(name: str, attrs: dict) -> str:
    """Best-effort ``ioos_category`` for a variable."""
    if "ioos_category" in attrs:
        return str(attrs["ioos_category"])
    low = name.lower()
    if low in ("time", "t"):
        return "Time"
    if low in _AXIS_ALIASES["lat"] or low in _AXIS_ALIASES["lon"]:
        return "Location"
    if low in ("depth", "z", "lev", "level", "altitude"):
        return "Location"
    haystack = " ".join(
        str(attrs.get(k, "")) for k in ("standard_name", "long_name")
    ).lower()
    haystack = f"{name.lower()} {haystack}"
    for pattern, category in _IOOS_BY_NAME:
        if re.search(pattern, haystack):
            return category
    return "Unknown"


@dataclass
class ErddapDataset:
    """One ERDDAP griddap dataset: a single rectangular hypercube."""

    dataset_id: str
    source_id: str
    ds: xr.Dataset
    dims: tuple[str, ...]
    data_vars: tuple[str, ...]
    globals_: dict = field(default_factory=dict)
    supplied_globals: tuple[str, ...] = ()

    @property
    def axes(self) -> dict[str, np.ndarray]:
        """Axis name -> values, in dimension order."""
        return {d: self.ds[d].values for d in self.dims}

    def variable_attrs(self, name: str) -> dict:
        """Attributes for ``name``, with ERDDAP's required extras filled in.

        Sorted as ERDDAP sorts them: alphabetically, ignoring case.
        """
        attrs = dict(self.ds[name].attrs)
        attrs.setdefault("ioos_category", infer_ioos_category(name, attrs))
        if name in self.dims:
            if "units" not in attrs:
                attrs["units"] = _axis_units(name, self.ds[name])
            # rerddap's info() reads actual_range off every variable
            attrs.setdefault("actual_range", self._actual_range(name))
        else:
            attrs.update(
                {k: v for k, v in _fill_attrs(self.ds[name]).items() if k not in attrs},
            )
        return {k: attrs[k] for k in sorted(attrs, key=lambda k: (k.lower(), k))}

    def _actual_range(self, name: str) -> np.ndarray | str:
        """ERDDAP-style ``actual_range``: ``[min, max]`` in the axis's dtype.

        Time axes give float64 epoch seconds. Kept numeric so each response
        can type and format it (``Float32 actual_range -89.975, 89.975``).
        """
        if name not in self.dims:  # never materialize a data variable
            return ""
        values = np.asarray(self.ds[name].values)
        if values.size == 0:
            return ""
        if np.issubdtype(values.dtype, np.datetime64):
            secs = values.astype("datetime64[s]").astype("float64")
            return np.array([secs.min(), secs.max()])
        nice = nice_doubles(values)
        return np.array([np.nanmin(nice), np.nanmax(nice)]).astype(values.dtype)

    def missing_required_globals(self) -> list[str]:
        """Required ERDDAP globals that the *source* did not supply.

        These are filled with placeholders so the dataset still loads, but a
        real deployment should provide them (ERDDAP's ``addAttributes``).
        """
        return [k for k in REQUIRED_GLOBALS if k not in self.supplied_globals]


def _fill_attrs(da: xr.DataArray) -> dict:
    """``_FillValue`` / ``missing_value``, which xarray keeps in ``.encoding``.

    Opening a netCDF or Zarr store moves both out of ``.attrs``, but clients
    read them from ERDDAP's metadata. They are given in the type of the
    values we serve. For packed data (``scale_factor``/``add_offset``) the
    served values are unpacked floats with NaN for missing, so the fill
    becomes NaN.
    """
    enc = da.encoding
    out = {}
    floating = da.dtype.kind == "f"
    packed = floating and ("scale_factor" in enc or "add_offset" in enc)
    for key in ("_FillValue", "missing_value"):
        value = enc.get(key)
        if value is None:
            continue
        value = np.asarray(np.nan if packed else value).reshape(-1)[0]
        if not floating and np.isnan(value):
            continue  # an integer variable cannot hold a NaN fill
        out[key] = value.astype(da.dtype)
    return out


_AXIS_ALIASES = {
    "lat": ("lat", "latitude", "y"),
    "lon": ("lon", "longitude", "x"),
}


@dataclass(frozen=True)
class AxisProblem:
    """An axis that ERDDAP would reject."""

    axis: str
    reason: str

    def __str__(self) -> str:
        """Human-readable description."""
        return f"axis {self.axis!r}: {self.reason}"


def check_axes(ds: xr.Dataset, dims: tuple[str, ...]) -> list[AxisProblem]:
    """Find axes ERDDAP would refuse.

    ERDDAP requires every axis to be strictly monotonic. Serving a
    non-monotonic axis anyway is worse than refusing: coordinate-value
    requests still look right (nearest-match lands on the first occurrence)
    while index ranges spanning the break silently return a series that jumps
    backwards in time, with no error for the user to notice.
    """
    problems: list[AxisProblem] = []
    for dim in dims:
        if dim not in ds:
            continue
        values = np.asarray(ds[dim].values)
        if values.size < _MIN_AXIS_LEN:
            continue
        numeric = (
            values.astype("datetime64[ns]").astype("int64")
            if np.issubdtype(values.dtype, np.datetime64)
            else values.astype("float64")
        )
        diffs = np.diff(numeric)
        if (diffs > 0).all() or (diffs < 0).all():
            continue
        bad = int(np.flatnonzero(diffs <= 0)[0]) if (diffs <= 0).any() else 0
        n_dup = int(values.size - np.unique(values).size)
        problems.append(
            AxisProblem(
                axis=dim,
                reason=(
                    f"not strictly monotonic; first break at index {bad} "
                    f"({values[bad]} -> {values[bad + 1]}), "
                    f"{n_dup} duplicate value(s) of {values.size}"
                ),
            ),
        )
    return problems


def _axis_units(name: str, da: xr.DataArray) -> str:
    """Units ERDDAP would infer for an axis that has none declared."""
    if np.issubdtype(getattr(da, "dtype", np.dtype("O")), np.datetime64):
        return "UTC"
    low = str(name).lower()
    if low in _AXIS_ALIASES["lat"]:
        return "degrees_north"
    if low in _AXIS_ALIASES["lon"]:
        return "degrees_east"
    if low in ("depth", "z", "lev", "level", "altitude"):
        return "m"
    return "1"


def nice_doubles(values: np.ndarray) -> np.ndarray:
    """Axis values as the doubles ERDDAP derives metadata from.

    ERDDAP rounds float32 values to 7 significant digits before computing
    ``actual_range``, the ``geospatial_*`` bounds and the average spacing
    (checked against real servers: erdMH1chla8day's latitude 89.979164
    becomes 89.97916). Other types are used as they are.
    """
    values = np.asarray(values)
    if values.dtype == np.float32:
        return np.array([float(f"{v:.7g}") for v in values.tolist()])
    return values.astype("float64")


#: ERDDAP's bounding-box globals: axis -> (name of the min, name of the max).
_MOST = {
    "lat": ("Southernmost_Northing", "Northernmost_Northing"),
    "lon": ("Westernmost_Easting", "Easternmost_Easting"),
}


def coverage_globals(
    ds: xr.Dataset,
    dims: tuple[str, ...],
    *,
    subset: bool = False,
) -> dict:
    """ACDD coverage globals that ERDDAP derives from the axes.

    ``rerddap``'s ``info()`` reads ``time_coverage_start``/``_end`` from the
    globals rather than from the time axis, so these are not optional.

    For the full dataset, bounds are doubles (see ``nice_doubles``) and the
    resolution is ``|last - first| / (n - 1)``. For a ``subset`` (a ``.nc``
    download) ERDDAP gives the subset's bounds in the axis's own dtype and
    keeps the full dataset's resolution, so no resolution is returned.
    """
    out: dict[str, object] = {}
    for dim in dims:
        if dim not in ds:
            continue
        values = np.asarray(ds[dim].values)
        if values.size == 0:
            continue
        if np.issubdtype(values.dtype, np.datetime64):
            stamps = pd.to_datetime([values.min(), values.max()])
            out["time_coverage_start"] = stamps[0].strftime("%Y-%m-%dT%H:%M:%SZ")
            out["time_coverage_end"] = stamps[1].strftime("%Y-%m-%dT%H:%M:%SZ")
            continue
        low = str(dim).lower()
        for axis, names in _AXIS_ALIASES.items():
            if low not in names:
                continue
            nice = nice_doubles(values)
            lo, hi = float(np.nanmin(nice)), float(np.nanmax(nice))
            if subset:
                lo, hi = values.dtype.type(lo), values.dtype.type(hi)
            elif values.size > 1:
                out[f"geospatial_{axis}_resolution"] = abs(nice[-1] - nice[0]) / (
                    values.size - 1
                )
            out[f"geospatial_{axis}_min"] = lo
            out[f"geospatial_{axis}_max"] = hi
            out[f"geospatial_{axis}_units"] = (
                "degrees_north" if axis == "lat" else "degrees_east"
            )
            out[_MOST[axis][0]] = lo
            out[_MOST[axis][1]] = hi
    return out


def _signature(da: xr.DataArray) -> tuple[str, ...]:
    return tuple(str(d) for d in da.dims)


def build_catalog(
    source_id: str,
    ds: xr.Dataset,
    *,
    metadata: dict | None = None,
    strict_axes: bool = True,
) -> list[ErddapDataset]:
    """Split one xarray Dataset into ERDDAP-compatible datasets.

    Variables are grouped by dimension signature. A source dataset with a
    single signature yields one ERDDAP dataset keeping the original id;
    multiple signatures yield one dataset each, suffixed with their
    non-horizontal dimension names.

    Args:
        source_id: the xpublish dataset id.
        ds: the source dataset.
        metadata: extra global attributes to merge in (the equivalent of
            ERDDAP's ``datasets.xml`` ``addAttributes``).
        strict_axes: when true (the default, matching ERDDAP), datasets whose
            axes are not strictly monotonic are dropped from the catalog with
            a logged warning rather than served with silently wrong results.

    Returns:
        One ``ErddapDataset`` per dimension signature, largest group first.
    """
    groups: dict[tuple[str, ...], list[str]] = {}
    for name, da in ds.data_vars.items():
        sig = _signature(da)
        if not sig:
            continue
        groups.setdefault(sig, []).append(str(name))

    # The "main" dataset keeps the plain id: most variables first, then the
    # simplest hypercube, then alphabetical so the result is deterministic.
    # Without the dimension-count term, a tie on variable count would hand the
    # plain id to whichever signature happened to sort first.
    ordered = sorted(
        groups.items(),
        key=lambda kv: (-len(kv[1]), len(kv[0]), kv[0]),
    )
    out: list[ErddapDataset] = []
    base_sig = ordered[0][0] if ordered else ()
    for sig, names in ordered:
        if sig == base_sig:
            # the largest group keeps the source id, so the common case is stable
            dataset_id = sanitize_id(source_id)
        else:
            extra = [d for d in sig if d not in base_sig]
            suffix = "_".join(extra) if extra else "_".join(sig)
            dataset_id = sanitize_id(f"{source_id}_{suffix}")

        keep = [n for n in names if all(d in ds.dims for d in sig)]
        sub = ds[keep]
        # keep only the coordinates that are this hypercube's axes
        sub = sub.drop_vars([c for c in sub.coords if c not in sig], errors="ignore")

        attrs = dict(ds.attrs)
        # xpublish tags every dataset with its id; not a real attribute
        attrs.pop("_xpublish_id", None)
        attrs.update(metadata or {})
        supplied = tuple(k for k in REQUIRED_GLOBALS if k in attrs)
        attrs.update(coverage_globals(sub, sig))
        attrs.setdefault("title", attrs.get("title", dataset_id))
        for key, value in _FALLBACK_GLOBALS.items():
            attrs.setdefault(key, value)
        sub.attrs = attrs

        problems = check_axes(sub, sig)
        if problems:
            detail = "; ".join(str(p) for p in problems)
            if strict_axes:
                logger.warning(
                    "ERDDAP: refusing dataset %r -- %s. "
                    "Fix the source data, or pass strict_axes=False to serve "
                    "it anyway (index ranges spanning the break will be wrong).",
                    dataset_id,
                    detail,
                )
                continue
            logger.warning(
                "ERDDAP: serving dataset %r with a bad axis -- %s",
                dataset_id,
                detail,
            )

        out.append(
            ErddapDataset(
                dataset_id=dataset_id,
                source_id=source_id,
                ds=sub,
                dims=sig,
                data_vars=tuple(keep),
                globals_=attrs,
                supplied_globals=supplied,
            ),
        )
    return out
