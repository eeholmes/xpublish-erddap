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
    "served_dtype",
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
    haystack = " ".join(str(attrs.get(k, "")) for k in ("standard_name", "long_name")).lower()
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
            da = self.ds[name]
            attrs.update({k: v for k, v in _fill_attrs(da).items() if k not in attrs})
            if not _is_packed(da):
                attrs.update(_typed_as_variable(attrs, served_dtype(da)))
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


def _is_packed(da) -> bool:
    """Whether xarray unpacked the variable with ``scale_factor``/``add_offset``."""
    enc = getattr(da, "encoding", {})
    return "scale_factor" in enc or "add_offset" in enc


def served_dtype(da) -> np.dtype:
    """The dtype a variable is served in, which is not always ``da.dtype``.

    xarray's default decoding turns an integer variable with a ``_FillValue``
    into floats, to hold NaN for the fill. ERDDAP serves such a variable in
    its stored integer type (a Byte ``mask`` stays Byte), so the stored type,
    kept in ``.encoding``, wins. Packed variables are served unpacked, as
    floats, as ERDDAP does.
    """
    dtype = np.dtype(da.dtype)
    stored = getattr(da, "encoding", {}).get("dtype")
    if dtype.kind == "f" and stored is not None and not _is_packed(da):
        stored = np.dtype(stored)
        if stored.kind in "iu":
            return stored
    return dtype


#: Attributes ERDDAP gives in the variable's own type (``EDV``'s constructor
#: converts the first four to the destination type). CF requires the same of
#: ``flag_values``/``flag_masks``, which arrive from Zarr's JSON as plain ints.
_TYPED_AS_VARIABLE = (
    "_FillValue",
    "missing_value",
    "valid_min",
    "valid_max",
    "valid_range",
    "flag_values",
    "flag_masks",
)


def _typed_as_variable(attrs: dict, dtype: np.dtype) -> dict:
    """``attrs``' fill, valid and flag values in ``dtype``, where they fit it."""
    if dtype.kind not in "iuf":
        return {}
    out = {}
    for key in _TYPED_AS_VARIABLE:
        value = attrs.get(key)
        if value is None or isinstance(value, str | bytes | bool | np.bool_):
            continue
        arr = np.asarray(value)
        if arr.dtype.kind not in "iuf" or (key.startswith("flag_") and dtype.kind == "f"):
            continue
        with np.errstate(all="ignore"):
            typed = arr.astype(dtype)
        if not np.array_equal(typed, arr, equal_nan=dtype.kind == "f" and arr.dtype.kind == "f"):
            continue  # it does not fit; leave it as the source gave it
        out[key] = typed if arr.ndim else typed[()]
    return out


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
    dtype = served_dtype(da)
    floating = dtype.kind == "f"
    packed = floating and _is_packed(da)
    for key in ("_FillValue", "missing_value"):
        value = enc.get(key)
        if value is None:
            continue
        value = np.asarray(np.nan if packed else value).reshape(-1)[0]
        if not floating and np.isnan(value):
            continue  # an integer variable cannot hold a NaN fill
        out[key] = value.astype(dtype)
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
            values.astype("datetime64[us]").astype("int64")
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
                out[f"geospatial_{axis}_resolution"] = abs(nice[-1] - nice[0]) / (values.size - 1)
            out[f"geospatial_{axis}_min"] = lo
            out[f"geospatial_{axis}_max"] = hi
            out[f"geospatial_{axis}_units"] = "degrees_north" if axis == "lat" else "degrees_east"
            out[_MOST[axis][0]] = lo
            out[_MOST[axis][1]] = hi
    return out


def tree_datasets(xpublish_id: str, tree: xr.DataTree) -> list[tuple[str, xr.Dataset]]:
    """The groups of a published DataTree that hold variables, as datasets.

    Since xpublish 0.5 everything published is a DataTree; a plain Dataset is
    a tree with only a root. Each group with data variables becomes a source
    for ``build_catalog``, named by the xpublish id plus the group path
    (``store`` and ``native/monthly`` give ``store/native/monthly``, which
    ``sanitize_id`` turns into ``store_native_monthly``). The root keeps the
    plain id. A group's dataset includes the coordinates it inherits from its
    parents, and only its own attributes, as when xarray opens one group.
    """
    out = []
    for node in tree.subtree:
        if not node.data_vars:
            continue
        path = node.relative_to(tree)
        source_id = xpublish_id if path == "." else f"{xpublish_id}/{path}"
        out.append((source_id, node.to_dataset()))
    return out


def unique_ids(entries: list[ErddapDataset]) -> dict[str, ErddapDataset]:
    """Index ``entries`` by datasetID, dropping every entry whose id is taken twice.

    Different sources can sanitize to the same datasetID (``a-b`` and ``a_b``,
    or a store ``x_y`` and the group ``y`` of a store ``x``). Serving either one
    under the shared id would hide the other, so both are left out, with an
    error naming the sources.
    """
    by_id: dict[str, list[ErddapDataset]] = {}
    for entry in entries:
        by_id.setdefault(entry.dataset_id, []).append(entry)
    out = {}
    for dataset_id, found in by_id.items():
        if len(found) == 1:
            out[dataset_id] = found[0]
            continue
        logger.error(
            "ERDDAP: refusing datasetID %r -- it names more than one source (%s). "
            "Rename a dataset or group so their ids differ.",
            dataset_id,
            ", ".join(repr(e.source_id) for e in found),
        )
    return out


def _signature(da: xr.DataArray) -> tuple[str, ...]:
    return tuple(str(d) for d in da.dims)


# -- ERDDAP's variable names --------------------------------------------------
#: ``EDV.LAT_UNITS_VARIANTS`` and ``LON_UNITS_VARIANTS``.
_LAT_UNITS = ("degrees_north", "degree_north", "degreeN", "degree_N", "degreesN", "degrees_N")
_LON_UNITS = (
    "degrees_east",
    "degree_east",
    "degreeE",  # codespell:ignore
    "degree_E",
    "degreesE",
    "degrees_E",
)

#: Names ERDDAP accepts as lat/lon on name alone; we also want degree units.
_BARE_XY = {"x", "y", "xax", "yax"}


def _could_be_degrees(units: str, *, east: bool) -> bool:
    """``EDV.couldBeLonUnits`` / ``couldBeLatUnits``, for non-empty units."""
    low = units.lower()
    if east and ("north" in low or "south" in low):
        return False
    if not east and ("east" in low or "west" in low):
        return False
    variants = _LON_UNITS if east else _LAT_UNITS
    words = ("degrees east", "degree west", "degrees west") if east else ("degrees north",)
    return (
        low in ("deg", "degree", "degrees")
        or "decimal degrees" in low
        or any(w in low for w in words)
        or low.startswith("ddd.d" if east else "dd.d")
        or low in variants
    )


def _named(name: str, *, east: bool) -> bool:
    """The name half of ``EDV.probablyLon`` / ``probablyLat``."""
    low = name.lower()
    if east:
        return (
            low.startswith("lon") or "longitude" in low or low in ("x", "xax")
        ) and not low.startswith(
            ("lone", "longl"),
        )
    return (
        low.startswith("lat") or "latitude" in low or low in ("y", "yax")
    ) and not low.startswith(
        ("latin", "lata", "late", "lath", "lato", "latt"),
    )


def _probably(name: str, units: str, *, east: bool) -> bool:
    """``EDV.probablyLon`` / ``probablyLat``, with bare ``x``/``y`` needing units.

    ERDDAP takes an axis named ``x`` or ``y`` with no units as longitude or
    latitude; a projected grid's metre axes often have none (#60), so here
    they need degree units.
    """
    if not _named(name, east=east):
        return False
    if not units:
        return name.lower() not in _BARE_XY
    return _could_be_degrees(units, east=east)


def recognised_axis(name: str, da: xr.DataArray) -> str | None:
    """``latitude``, ``longitude`` or ``time`` if axis ``name`` is clearly that axis.

    Lat/lon: ``standard_name``, CF degree units (``EDV.LAT_UNITS_VARIANTS``),
    or ERDDAP's own name-and-units test (``EDV.probablyLat``/``probablyLon``,
    which ``EDD.suggestDestinationName`` uses to rename axes in
    GenerateDatasetsXml). An axis whose ``standard_name`` says it is something
    else (``grid_latitude`` on a rotated grid) is not lat/lon, nor is one
    whose name and units disagree (``lat`` in ``degrees_east``). Time: a
    datetime axis. A numeric axis with CF time units is not renamed, since we
    serve its numbers as they are and ERDDAP's ``time`` is always UTC
    timestamps; a timedelta axis (``lead_time``) is not time.
    """
    if np.issubdtype(da.dtype, np.datetime64):
        return "time"
    if da.dtype.kind not in "iuf":
        return None
    standard_name = str(da.attrs.get("standard_name", ""))
    units = str(da.attrs.get("units", "")).strip()
    for target, east, variants in (
        ("latitude", False, _LAT_UNITS),
        ("longitude", True, _LON_UNITS),
    ):
        if standard_name == target:
            return target
        if standard_name:
            continue  # says it is something else
        if units in variants and not _named(name, east=not east):
            return target
        if _probably(name, units, east=east):
            return target
    return None


def is_variable_name_safe(name: str) -> bool:
    """``String2.isVariableNameSafe``: a letter or ``_``, then letters, digits, ``_``.

    ERDDAP's letters are ISO 8859-1 letters; ours are ASCII, which is what
    our constraint parser reads.
    """
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None


def safe_variable_name(name: str) -> str:
    """The name ERDDAP's GenerateDatasetsXml would give a variable.

    ``EDD.suggestDestinationName``'s last step: every unsafe character becomes
    ``_``, a name not starting with a letter gets ``a_`` in front, runs of
    ``_`` collapse and trailing ones go (``sst-anom`` -> ``sst_anom``,
    ``1st`` -> ``a_1st``).
    """
    out = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not out[:1].isascii() or not out[:1].isalpha():
        out = f"a_{out}"
    out = re.sub(r"_+", "_", out).rstrip("_")
    return out or "a"


def served_names(
    ds: xr.Dataset,
    dims: tuple[str, ...],
    data_vars: list[str],
    *,
    dataset_id: str,
    rename_axes: bool | dict[str, str] = True,
) -> tuple[dict[str, str], list[str]] | None:
    """The names one hypercube is served under: ``(renames, refused)``.

    ``renames`` maps source names to served names, for ``Dataset.rename``.
    Recognised axes get ERDDAP's names (``recognised_axis``), or with a dict
    ``rename_axes`` the names it gives; ``False`` keeps them all. A name ERDDAP
    cannot serve (``sst-anom``) gets ``safe_variable_name``. A served name
    already taken is not used: an axis keeps its own name, a data variable
    that cannot be served is ``refused``. ``None`` means the whole hypercube
    must be refused (an axis with an unservable name).
    """
    taken = set(dims) | set(data_vars)
    renames: dict[str, str] = {}

    def claim(source: str, target: str) -> bool:
        if target in taken:
            return False
        taken.discard(source)
        taken.add(target)
        renames[source] = target
        return True

    for dim in dims:
        if isinstance(rename_axes, dict):
            target = rename_axes.get(dim)
        else:
            target = recognised_axis(dim, ds[dim]) if rename_axes else None
        if target is None or target == dim:
            continue
        if not is_variable_name_safe(target):
            logger.warning(
                "ERDDAP: dataset %r -- cannot serve axis %r as %r, not a valid name",
                dataset_id,
                dim,
                target,
            )
        elif not claim(dim, target):
            logger.warning(
                "ERDDAP: dataset %r -- serving axis %r under its own name, "
                "as %r is taken by another variable",
                dataset_id,
                dim,
                target,
            )

    refused = []
    for name in (*dims, *data_vars):
        if name in renames or is_variable_name_safe(name):
            continue
        target = safe_variable_name(name)
        if claim(name, target):
            continue
        if name in dims:
            logger.warning(
                "ERDDAP: refusing dataset %r -- axis %r is not a valid ERDDAP name and %r is taken",
                dataset_id,
                name,
                target,
            )
            return None
        logger.warning(
            "ERDDAP: dataset %r -- leaving out variable %r: "
            "not a valid ERDDAP name and %r is taken",
            dataset_id,
            name,
            target,
        )
        refused.append(name)
    return renames, refused


def build_catalog(
    source_id: str,
    ds: xr.Dataset,
    *,
    metadata: dict | None = None,
    strict_axes: bool = True,
    rename_axes: bool | dict[str, str] = True,
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
        rename_axes: serve recognised latitude, longitude and time axes as
            ``latitude``, ``longitude`` and ``time``, as ERDDAP does (the
            default); ``False`` keeps source names; a dict maps source axis
            names to served names instead. See ``served_names``. DatasetIDs
            come from the source names either way, so this does not move them.

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
    for source_sig, names in ordered:
        if source_sig == base_sig:
            # the largest group keeps the source id, so the common case is stable
            dataset_id = sanitize_id(source_id)
        else:
            extra = [d for d in source_sig if d not in base_sig]
            suffix = "_".join(extra) if extra else "_".join(source_sig)
            dataset_id = sanitize_id(f"{source_id}_{suffix}")

        keep = [n for n in names if all(d in ds.dims for d in source_sig)]
        sub = ds[keep]
        # keep only the coordinates that are this hypercube's axes
        sub = sub.drop_vars([c for c in sub.coords if c not in source_sig], errors="ignore")

        named = served_names(sub, source_sig, keep, dataset_id=dataset_id, rename_axes=rename_axes)
        if named is None:
            continue
        renames, refused = named
        if refused:
            keep = [n for n in keep if n not in refused]
            if not keep:
                continue
            sub = sub.drop_vars(refused)
        # lazy: the served names point at the same source arrays
        sub = sub.rename(renames)
        keep = [renames.get(n, n) for n in keep]
        sig = tuple(renames.get(d, d) for d in source_sig)

        attrs = dict(ds.attrs)
        # xpublish tags every dataset with its id; not a real attribute
        attrs.pop("_xpublish_id", None)
        attrs.update(metadata or {})
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
            ),
        )
    return out
