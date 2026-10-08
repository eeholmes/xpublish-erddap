"""Time axes ERDDAP would not accept, converted as an ERDDAP admin would.

ERDDAP serves time only as Gregorian ``seconds since 1970-01-01T00:00:00Z``
and never reads a variable's ``calendar`` (``EDVTimeStampGridAxis`` converts
with ``Calendar2.getTimeBaseAndFactor``, a base and a factor), so a model
calendar on a real ERDDAP is served days or months off. This package does not
copy that, and does not refuse such axes either: it serves what an admin
would have converted the axis to before ERDDAP accepted it (#60).

- A cftime axis (``noleap``, ``360_day``, ``julian``, ...) keeps each step's
  date label: noleap 2010-06-15 is served as 2010-06-15. When some labels are
  not real dates (Feb 30 in ``360_day``, Feb 29 of a non-leap year), every
  step is mapped by its position in the year instead, so no step is lost and
  indices do not move.
- A timedelta axis (``lead_time``) is served as numbers in its source units.

Only the 1-D axis is converted; the data stays lazy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

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

_LABELS = "each date label kept"


def _is_cftime(values: np.ndarray) -> bool:
    if values.dtype != object or values.size == 0:
        return False
    first = values.flat[0]
    return hasattr(first, "calendar") and hasattr(first, "timetuple")


def _us(delta: timedelta) -> int:
    """A ``timedelta`` in whole microseconds, exactly."""
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _label(d) -> np.datetime64:
    """The same date and time of day on the proleptic Gregorian calendar.

    Raises ``ValueError`` when the label is not a real date (Feb 30).
    """
    # datetime checks the date; numpy would roll Feb 30 over to Mar 2
    when = datetime(d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond)  # noqa: DTZ001
    return np.datetime64(when, "us")


def _year_lengths(d) -> tuple[timedelta, timedelta]:
    """The length of ``d``'s year in its own calendar, and in the Gregorian."""
    start = d.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    own = start.replace(year=d.year + 1) - start
    return own, datetime(d.year + 1, 1, 1) - datetime(d.year, 1, 1)  # noqa: DTZ001


def _by_day_of_year(d) -> np.datetime64:
    """xarray's ``convert_calendar(align_on="year")``: the nearest Gregorian day.

    ``calendar_ops._interpolate_day_of_year``: day of year ``n`` becomes
    ``round(n * days_to / days_from)``, keeping the time of day. From a
    360-day year every day lands on its own date.
    """
    own, gregorian = _year_lengths(d)
    day = round(d.dayofyr * gregorian.days / own.days)
    when = datetime(d.year, 1, 1, d.hour, d.minute, d.second, d.microsecond)  # noqa: DTZ001
    return np.datetime64(when + timedelta(days=day - 1), "us")


def _by_year_fraction(d) -> np.datetime64:
    """``d`` at the same fraction of its year, to the microsecond.

    For when whole days collide (a 366-day year has more days than 365).
    """
    own, gregorian = _year_lengths(d)
    start = d.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    shifted = round(_us(d - start) * _us(gregorian) / _us(own))
    return np.datetime64(datetime(d.year, 1, 1), "us") + np.timedelta64(shifted, "us")  # noqa: DTZ001


def _distinct_in_order(values: np.ndarray, source: np.ndarray) -> bool:
    """Whether converting kept every step distinct and in the source's order."""
    if values.size < 2:  # noqa: PLR2004
        return True
    ups = np.diff(values) > np.timedelta64(0, "us")
    was_up = np.array([b > a for a, b in zip(source.flat[:-1], source.flat[1:], strict=True)])
    return bool((ups == was_up).all() and (np.diff(values) != np.timedelta64(0, "us")).all())


def cftime_to_datetime64(values: np.ndarray) -> tuple[np.ndarray, str]:
    """Gregorian ``datetime64[us]`` for a cftime axis, and how it was mapped.

    The date labels when they are all real dates; otherwise the nearest day
    by position in the year, as xarray's ``convert_calendar`` does; otherwise
    (two steps on one day) the exact fraction of the year.
    """
    try:
        return np.array([_label(d) for d in values.flat], dtype="datetime64[us]"), _LABELS
    except ValueError:
        pass
    out = np.array([_by_day_of_year(d) for d in values.flat], dtype="datetime64[us]")
    if _distinct_in_order(out, values):
        return out, "each day moved to the nearest day at the same place in the year"
    out = np.array([_by_year_fraction(d) for d in values.flat], dtype="datetime64[us]")
    return out, "each step kept at the same fraction of its year"


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

    ``None`` when an axis has no Gregorian equivalent (a year before 1), which
    is logged; the dataset is then refused.

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
            log = logger.warning if how != _LABELS else logger.info
            log("ERDDAP: dataset %r -- axis %r: %s", dataset_id, dim, note)
            new[dim] = xr.Variable(dim, served, attrs)
        elif np.issubdtype(values.dtype, np.timedelta64):
            served, units = _timedelta_numbers(da)
            attrs["units"] = units
            new[dim] = xr.Variable(dim, served, attrs)
    if not new:
        return ds
    return ds.assign_coords(new)
