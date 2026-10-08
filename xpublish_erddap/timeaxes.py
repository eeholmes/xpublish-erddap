"""Time axes ERDDAP would not accept, converted as an ERDDAP admin would.

ERDDAP serves time only as Gregorian ``seconds since 1970-01-01T00:00:00Z``
and never reads a variable's ``calendar`` (``EDVTimeStampGridAxis`` converts
with ``Calendar2.getTimeBaseAndFactor``, a base and a factor), so a model
calendar on a real ERDDAP is served days or months off. This package does not
copy that: it serves what an admin would have converted the axis to before
ERDDAP accepted it (#60). The rule (EH): a format or calendar may change, a
time may not.

- A real calendar (``julian``, ``standard`` before 1582) is converted by
  moment: Julian 1900-01-01 is served as Gregorian 1900-01-13.
- A model calendar (``noleap``, ``360_day``, ``all_leap``, ...) has no moments,
  only labels, so each label is kept: noleap 2010-06-15 is 2010-06-15. An axis
  with a label that is not a real date (Feb 30 in ``360_day``, Feb 29 2001 in
  ``all_leap``) has no Gregorian equivalent and is refused.
- A timedelta axis (``lead_time``) is served as numbers in its source units.

Only the 1-D axis is converted; the data stays lazy.
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import xarray as xr

__all__ = ["servable_axes"]

logger = logging.getLogger("uvicorn")

#: CF names of the units xarray decodes a timedelta from, as numpy units.
_TIMEDELTA_UNITS = {
    "days": "D",
    "hours": "h",
    "minutes": "m",
    "seconds": "s",
    "milliseconds": "ms",
    "microseconds": "us",
    "nanoseconds": "ns",
}

#: Calendars of real moments, which convert to Gregorian time by moment.
_REAL_CALENDARS = {"standard", "gregorian", "julian", "proleptic_gregorian"}

_LABELS = "each date label kept"
_MOMENTS = "each moment kept"


def _is_cftime(values: np.ndarray) -> bool:
    if values.dtype != object or values.size == 0:
        return False
    first = values.flat[0]
    return hasattr(first, "calendar") and hasattr(first, "timetuple")


def _label(d) -> np.datetime64:
    """The same date and time of day on the proleptic Gregorian calendar.

    Raises ``ValueError`` when the label is not a real date (Feb 30).
    """
    # datetime checks the date; numpy would roll Feb 30 over to Mar 2
    try:
        when = datetime(d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond)  # noqa: DTZ001
    except ValueError:
        msg = f"{d.strftime('%Y-%m-%d')} is not a Gregorian date"
        raise ValueError(msg) from None
    return np.datetime64(when, "us")


def cftime_to_datetime64(values: np.ndarray) -> tuple[np.ndarray, str]:
    """Gregorian ``datetime64[us]`` for a cftime axis, and how it was mapped.

    Raises ``ValueError``, naming the first such date, when a step has no
    Gregorian equivalent.
    """
    calendar = values.flat[0].calendar
    if calendar in _REAL_CALENDARS:
        # cftime's change_calendar keeps the moment and changes the label
        gregorian = [d.change_calendar("proleptic_gregorian") for d in values.flat]
        return np.array([_label(d) for d in gregorian], dtype="datetime64[us]"), _MOMENTS
    return np.array([_label(d) for d in values.flat], dtype="datetime64[us]"), _LABELS


def _timedelta_numbers(da: xr.DataArray) -> tuple[np.ndarray, str]:
    """A timedelta axis as numbers in its source units (``hours``)."""
    units = str(da.encoding.get("units", "seconds")).strip().lower()
    step = _TIMEDELTA_UNITS.get(units)
    if step is None:
        units, step = "seconds", "s"
    values = np.asarray(da.values) / np.timedelta64(1, step)
    source = np.dtype(da.encoding.get("dtype", "float64"))
    if source.kind in "iu" and np.all(values == np.round(values)):
        values = values.astype(source)
    return values, units


def servable_axes(ds: xr.Dataset, dims: tuple[str, ...], *, dataset_id: str) -> xr.Dataset | None:
    """``ds`` with its cftime and timedelta axes converted for ERDDAP.

    ``None`` when a step has no Gregorian equivalent (Feb 30, a year before
    1), which is logged; the dataset is then refused.

    A converted time axis is a ``datetime64`` axis like any decoded one: no
    ``calendar`` attribute (a client that read one next to ERDDAP's units
    would shift every date again) and a ``comment`` saying what was done.
    """
    new = {}
    for dim in dims:
        if dim not in ds.coords:
            continue
        da = ds[dim]
        values = np.asarray(da.values)
        attrs = {k: v for k, v in da.attrs.items() if k not in ("calendar", "units")}
        if _is_cftime(values):
            calendar = values.flat[0].calendar
            try:
                served, how = cftime_to_datetime64(values)
            except ValueError as err:
                logger.warning(
                    "ERDDAP: refusing dataset %r -- axis %r (%r calendar) has no "
                    "Gregorian equivalent: %s",
                    dataset_id,
                    dim,
                    calendar,
                    err,
                )
                return None
            note = (
                f"Converted from the {calendar!r} calendar to Gregorian time, "
                f"{how} (xpublish-erddap)."
            )
            attrs["comment"] = f"{attrs['comment']} {note}" if attrs.get("comment") else note
            logger.info("ERDDAP: dataset %r -- axis %r: %s", dataset_id, dim, note)
            new[dim] = xr.Variable(dim, served, attrs)
        elif np.issubdtype(values.dtype, np.timedelta64):
            served, units = _timedelta_numbers(da)
            attrs["units"] = units
            new[dim] = xr.Variable(dim, served, attrs)
    if not new:
        return ds
    return ds.assign_coords(new)
