"""ERDDAP's dataset table and advanced search (#27, #4).

Ported from ERDDAP's own source (github.com/ERDDAP/erddap, ``main`` read on
2026-10-07): ``Erddap.makePlainDatasetTable`` (the table), ``EDD.extendedSummary``
(its Summary column), ``Erddap.doAdvancedSearch`` (the filters),
``LoadDatasets.categorize*Atts`` (the category values they match), and the
default "original" search engine for ``searchFor`` (``Erddap.getSearchDatasetIDs``,
``EDD.searchRank``, ``EDD.searchString``; ``setup.xml``'s default). The same
table answers ``search/index``, ``search/advanced``, ``griddap/index`` and
``info/index``. ``Erddap.doCategorize`` (with ``categorizeOptionsTable`` and
``sendCategoryPftOptionsTable``) is the browse-by-category API (#5).
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd
from fastapi import HTTPException

from xpublish_erddap import formats
from xpublish_erddap.catalog import ErddapDataset

#: ERDDAP's dataset-table columns on a server with WMS, files, FGDC and ISO 19115
#: on, and SOS, WCS, logins and subscriptions off: the configuration of
#: coastwatch.noaa.gov and polarwatch (EH's choice, 2026-10-07). Other servers
#: add ``Email`` (subscriptions) or ``Accessible`` (logins); this plugin has
#: neither.
DATASET_COLUMNS = [
    "griddap",
    "Subset",
    "tabledap",
    "Make A Graph",
    "wms",
    "files",
    "Title",
    "Summary",
    "FGDC",
    "ISO 19115",
    "Info",
    "Background Info",
    "RSS",
    "Institution",
    "Dataset ID",
]

#: ERDDAP's default ``categoryAttributes``, as advanced search names them.
#: ``variableName`` is the variable's own name, not an attribute.
GLOBAL_CATEGORIES = ("cdm_data_type", "institution", "keywords")
VARIABLE_CATEGORIES = ("ioos_category", "long_name", "standard_name", "variableName")

#: ERDDAP's default ``categoryAttributes``, in the order of ``setup.xml``
#: (``development/jetty/config/``): ``global:cdm_data_type, global:institution,
#: ioos_category, global:keywords, long_name, standard_name, variableName``.
#: These are also the names in the URL (``EDConfig.categoryAttributesInURLs``,
#: the same after ``String2.modifyToBeFileNameSafe``).
CATEGORY_ATTRIBUTES = (
    "cdm_data_type",
    "institution",
    "ioos_category",
    "keywords",
    "long_name",
    "standard_name",
    "variableName",
)

#: Protocols an advanced search may name, as on a server with WMS on. No dataset
#: here is served by WMS, so ``protocol=WMS`` matches none; SOS and WCS are
#: refused, as by a server without them.
PROTOCOLS = ("griddap", "tabledap", "wms")

#: ERDDAP's ``(ANY)``, meaning "no constraint".
ANY = "(ANY)"

#: ERDDAP's ``EDStatic.defaultItemsPerPage``.
ITEMS_PER_PAGE = 1000

_TIME_UNITS = {
    "second": "seconds",
    "minute": "minutes",
    "hour": "hours",
    "day": "days",
    "month": "months",
    "year": "years",
}


def no_matches(detail: str = "nRows = 0") -> HTTPException:
    """ERDDAP's 404 for an advanced search with no results."""
    return HTTPException(404, f"Your query produced no matching results. ({detail})")


def no_search_matches(search_for: str) -> HTTPException:
    """ERDDAP's 404 for a plain search with no results (``EDStatic.noSearchMatch``).

    It suggests fewer words when the search has a space in it.
    """
    search_for = search_for.strip()
    hint = "Check the spelling of the word(s) you searched for." if search_for else ""
    if " " in search_for:
        hint += " Try using fewer search words."
    return HTTPException(
        404,
        f"Resource not found: Your query produced no matching results. {hint}".strip(),
    )


# -- the table ----------------------------------------------------------------


def dataset_row(ed: ErddapDataset, base: str, ext: str) -> list[str]:
    """One dataset's row, empty where this plugin has no such service."""
    g = ed.globals_
    return [
        f"{base}/griddap/{ed.dataset_id}",
        "",  # Subset: tabledap only
        "",  # tabledap
        "",  # Make A Graph
        "",  # wms
        "",  # files
        str(g.get("title", ed.dataset_id)),
        extended_summary(ed),
        "",  # FGDC
        "",  # ISO 19115
        f"{base}/info/{ed.dataset_id}/index.{ext}",
        str(g.get("infoUrl", "")),
        "",  # RSS
        str(g.get("institution", "")),
        ed.dataset_id,
    ]


def by_title(datasets: list[ErddapDataset]) -> list[ErddapDataset]:
    """In ERDDAP's listing order: by title, ignoring case."""
    return sorted(
        datasets,
        key=lambda d: (
            str(d.globals_.get("title", d.dataset_id)).lower(),
            d.dataset_id,
        ),
    )


def no_long_lines_at_space(text: str, max_length: int = 100) -> str:
    """ERDDAP's ``String2.noLongLinesAtSpace``: wrap lines at a space.

    Only the number of lines is used (it decides where the variable list is
    cut), so this follows ERDDAP's algorithm rather than ``textwrap``.
    """
    n = len(text)
    if n <= max_length:
        return text
    out = []
    min_count = max_length // 2
    start = 0
    count = 0
    last_space = -1
    i = 0
    while i < n:
        ch = text[i]
        if ch == "\n":
            out.append(text[start : i + 1])
            start = i + 1
            count = 0
            last_space = -1
        else:
            if ch == " " and count >= min_count:
                last_space = i
            count += 1
            if count >= max_length and last_space >= 0:
                out.append(text[start:last_space] + "\n")
                i = last_space
                last_space = -1
                count = 0
                while i < n - 1 and text[i + 1] == " ":
                    i += 1
                start = i + 1
        i += 1
    if start < n:
        out.append(text[start:])
    return "".join(out)


def _long_name(attrs: dict, name: str) -> str:
    """ERDDAP's ``EDV.longName``: long_name, else standard_name, else the name."""
    for key in ("long_name", "standard_name"):
        if attrs.get(key) is not None:
            return str(attrs[key])
    return name


def extended_summary(ed: ErddapDataset) -> str:
    """ERDDAP's ``EDD.extendedSummary``: the summary plus a list of variables."""
    summary = str(ed.globals_.get("summary", ""))
    n_lines = no_long_lines_at_space(summary).count("\n")
    if summary.endswith("\n\n"):
        part = ""
    elif summary.endswith("\n"):
        part, n_lines = "\n", n_lines + 1
    else:
        part, n_lines = "\n\n", n_lines + 2
    part += f"cdm_data_type = {ed.globals_.get('cdm_data_type', 'Grid')}\n"
    part += "VARIABLES (all of which use the dimensions "
    part += "".join(f"[{d}]" for d in ed.dims) + "):\n"
    n_lines += 2
    names = list(ed.data_vars)
    for i, name in enumerate(names):
        attrs = ed.ds[name].attrs
        long_name = _long_name(attrs, name)
        # ERDDAP compares lengths, not text: "sst" and "SST" both drop out
        long_name = "" if len(long_name) == len(name) else long_name
        units = "" if attrs.get("units") is None else str(attrs["units"])
        glue = ", " if long_name and units else ""
        detail = f" ({long_name}{glue}{units})" if long_name or units else ""
        part += f"{name}{detail}\n"
        n_lines += 1
        if n_lines > 30 and i < len(names) - 4:  # noqa: PLR2004 (ERDDAP's numbers)
            part += f"... ({len(names) - i - 1} more variables)\n"
            break
    return summary + part


# -- searchFor ----------------------------------------------------------------


def _attr_lines(attrs: dict) -> list[str]:
    """Attributes as ERDDAP's ``Attributes.toString`` lists them, sorted."""
    lines = []
    for key in sorted(attrs, key=lambda k: (k.lower(), k)):
        if key == "_xpublish_id":
            continue
        value = attrs[key]
        if isinstance(value, np.ndarray | list | tuple):
            value = ", ".join(str(v) for v in np.asarray(value).ravel())
        lines.append(f"{key}={value}")
    return lines


def _variable_lines(ed: ErddapDataset, name: str) -> list[str]:
    attrs = ed.ds[name].attrs
    return [
        f"variableName={name}",
        f"sourceName={name}",
        f"long_name={_long_name(attrs, name)}",
        f"type={formats.erddap_type(ed.ds[name])}",
    ]


def search_text(ed: ErddapDataset) -> str:
    """ERDDAP's ``searchString`` for a grid dataset, in lower case.

    Its order matters: a word found earlier ranks higher. Title and id, then
    the data variables' names, then all attributes, then the axes. Built once
    per dataset, as ERDDAP builds it once per load.
    """
    return ed.memo("search_text", lambda: _search_text(ed))


def _search_text(ed: ErddapDataset) -> str:
    lines = [
        "all",
        f"title={ed.globals_.get('title', ed.dataset_id)}",
        f"datasetID={ed.dataset_id}",
        "protocol=griddap",
    ]
    for name in ed.data_vars:
        lines += _variable_lines(ed, name)
    lines += _attr_lines(ed.globals_)
    for name in ed.data_vars:
        lines += _attr_lines(ed.variable_attrs(name))
    for name in ed.dims:
        lines += _variable_lines(ed, name)
    for name in ed.dims:
        lines += _attr_lines(ed.variable_attrs(name))
    return "\n".join(lines).replace('"', "").lower()


def search_words(search_for: str) -> list[tuple[bool, str]]:
    """ERDDAP's ``wordsAndQuotedPhrases``, with ``-`` marking words to exclude.

    Words are separated by white space or commas; ``"a phrase"`` is one word,
    with ``""`` for a quote inside it.
    """
    out = []
    pattern = r'(-?)"((?:[^"]|"")*)"?|([^\s,"]+)'
    for dash, phrase, word in re.findall(pattern, search_for.lower()):
        if word:
            negative, text = word.startswith("-"), word.removeprefix("-")
        else:
            negative, text = bool(dash), phrase.replace('""', '"')
        text = text.strip()
        if text:
            out.append((negative, text))
    return out


def text_search(datasets: list[ErddapDataset], search_for: str) -> list[ErddapDataset]:
    """ERDDAP's original search engine: every word found, none of the ``-`` ones.

    Ranked as ERDDAP ranks: by the summed positions of the words in each
    dataset's search text (in tens), then by title. A title containing
    DEPRECATED sorts last. No words, or just ``all``, lists every dataset.
    """
    words = search_words(search_for)
    if not words or words == [(False, "all")]:
        return by_title(datasets)
    ranked = []
    for ed in datasets:
        text = search_text(ed)
        rank = 0
        for negative, word in words:
            position = text.find(word)
            if (position >= 0) == negative:
                break
            rank += max(position, 0)
        else:
            title = str(ed.globals_.get("title", ed.dataset_id))
            if "DEPRECATED" in title:
                rank += 10000
            ranked.append((rank // 10, title, ed.dataset_id, ed))
    ranked.sort(key=lambda r: r[:3])
    return [r[3] for r in ranked]


# -- categories ---------------------------------------------------------------


def file_name_safe(text: str) -> str:
    """ERDDAP's ``String2.modifyToBeFileNameSafe`` (A-Z, a-z, 0-9, _, - and .)."""
    if not text:
        return "_"
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "replace").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", ascii_text)
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe


def _keywords(value: str) -> list[str]:
    """ERDDAP's split of ``keywords``: by comma, lower case, no GCMD prefix."""
    out = []
    for part in value.split(","):
        word = part.strip().strip('"').lower()
        if not word:
            continue
        word = word.removeprefix("earth science > ")
        out.append(file_name_safe(word))
    return out


def categories(ed: ErddapDataset) -> dict[str, set[str]]:
    """Every category value of a dataset, as ERDDAP's advanced search matches them.

    Global attributes, then each data and axis variable's attributes (with the
    ``ioos_category`` this plugin fills in), cleaned up as ERDDAP does: file-
    name-safe and lower case. A missing value is ``_null``, as in ERDDAP.
    Built once per dataset; do not change what it returns.
    """
    return ed.memo("categories", lambda: _categories(ed))


def _categories(ed: ErddapDataset) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for att in GLOBAL_CATEGORIES:
        value = ed.globals_.get(att)
        if value is None:
            out[att] = {"_null"}
        elif att == "keywords":
            out[att] = set(_keywords(str(value)))
        else:
            out[att] = {file_name_safe(str(value)).lower()}
    for att in VARIABLE_CATEGORIES:
        values = set()
        for name in (*ed.data_vars, *ed.dims):
            attrs = ed.variable_attrs(name)
            value = name if att == "variableName" else attrs.get(att)
            values.add("_null" if value is None else file_name_safe(str(value)).lower())
        out[att] = values
    return out


# -- advanced search ----------------------------------------------------------


def _number(params: dict[str, str], key: str) -> float:
    """A bound, or NaN if unset or ``(ANY)``, as ERDDAP's ``parseDouble``."""
    value = params.get(key, "").strip()
    try:
        return float(value)
    except ValueError:
        return float("nan")


def _time(params: dict[str, str], key: str) -> float:
    """A time bound in epoch seconds, or NaN if unset.

    ISO 8601, epoch seconds, or ERDDAP's ``now-7days`` style. Strict, as
    ERDDAP is for non-HTML requests: a bad value is a 400.
    """
    value = params.get(key, "").strip()
    if not value:
        return float("nan")
    try:
        if value.lower().startswith("now"):
            return _now(value)
        try:
            return float(value)
        except ValueError:
            stamp = pd.Timestamp(value)
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize("UTC")
            return stamp.timestamp()
    except ValueError as err:
        raise HTTPException(
            400,
            f"Query error: {key}={value} is not a valid time.",
        ) from err


def _now(value: str) -> float:
    """ERDDAP's ``now``, ``now-7days``, ``now+1hour``."""
    match = re.fullmatch(
        r"now(?:([+-])(\d+)\s*([a-z]+?)s?)?",
        value.lower().replace(" ", ""),
    )
    if not match or (match.group(3) and match.group(3) not in _TIME_UNITS):
        raise ValueError(value)
    now = pd.Timestamp.now(tz="UTC").floor("s")
    if match.group(1):
        offset = pd.DateOffset(**{_TIME_UNITS[match.group(3)]: int(match.group(2))})
        now = now + offset if match.group(1) == "+" else now - offset
    return now.timestamp()


def _ordered(
    params: dict[str, str],
    low: str,
    high: str,
    *,
    time: bool = False,
) -> tuple:
    get = _time if time else _number
    lo, hi = get(params, low), get(params, high)
    if not np.isnan(lo) and not np.isnan(hi) and lo > hi:
        shown = (params[low], params[high]) if time else (lo, hi)
        raise HTTPException(400, f"Query error: {low}={shown[0]} > {high}={shown[1]}")
    return lo, hi


def _range(ed: ErddapDataset, axis: str) -> tuple[float, float] | None:
    """A dataset's (min, max) on its lon, lat or time axis, or None if it has none."""
    g = ed.globals_
    if axis == "time":
        if "time_coverage_start" not in g:
            return None
        return (
            pd.Timestamp(g["time_coverage_start"]).timestamp(),
            pd.Timestamp(g["time_coverage_end"]).timestamp(),
        )
    if f"geospatial_{axis}_min" not in g:
        return None
    return float(g[f"geospatial_{axis}_min"]), float(g[f"geospatial_{axis}_max"])


def _overlaps(ed: ErddapDataset, axis: str, lo: float, hi: float) -> bool:
    """ERDDAP's test: drop a dataset only if its range is wholly outside."""
    if np.isnan(lo) and np.isnan(hi):
        return True
    found = _range(ed, axis)
    if found is None:
        return False
    dmin, dmax = found
    if not np.isnan(lo) and lo > dmax:
        return False
    return np.isnan(hi) or hi >= dmin


def advanced_filter(
    datasets: list[ErddapDataset],
    params: dict[str, str],
) -> list[ErddapDataset]:
    """Apply advanced search's protocol, category and bounds constraints.

    ``searchFor`` is applied afterwards, by the caller, as ERDDAP does.
    """
    protocol = params.get("protocol", "").strip()
    if protocol and protocol != ANY:
        if protocol.lower() not in PROTOCOLS:
            raise no_matches(f"protocol={protocol}")
        if protocol.lower() != "griddap":
            datasets = []

    lon = _ordered(params, "minLon", "maxLon")
    lat = _ordered(params, "minLat", "maxLat")
    when = _ordered(params, "minTime", "maxTime", time=True)

    wanted = {
        att: params[att].strip().lower()
        for att in (*GLOBAL_CATEGORIES, *VARIABLE_CATEGORIES)
        if params.get(att, "").strip() not in {"", ANY}
    }
    if wanted:
        cats = {d.dataset_id: categories(d) for d in datasets}
        for att, value in wanted.items():
            # A value no dataset has is an error; one that only others have is
            # just no match.
            if not any(value in c[att] for c in cats.values()):
                raise no_matches(f"{att}={params[att].strip()}")
        datasets = [
            d
            for d in datasets
            if all(value in cats[d.dataset_id][att] for att, value in wanted.items())
        ]

    return [
        d
        for d in datasets
        if _overlaps(d, "lon", *lon) and _overlaps(d, "lat", *lat) and _overlaps(d, "time", *when)
    ]


def page_params(params: dict[str, str]) -> tuple[int, int]:
    """ERDDAP's ``page`` and ``itemsPerPage`` (1-based; 1000 per page by default)."""
    try:
        page = max(1, int(params.get("page", 1)))
        per_page = max(1, int(params.get("itemsPerPage", ITEMS_PER_PAGE)))
    except ValueError as err:
        raise HTTPException(
            400,
            "Query error: page and itemsPerPage must be integers.",
        ) from err
    return page, per_page


def page_of(datasets: list, params: dict[str, str]) -> list:
    """Page ``page`` of ``datasets``, ``itemsPerPage`` to a page."""
    page, per_page = page_params(params)
    start = (page - 1) * per_page
    return datasets[start : start + per_page]


# -- categorize ---------------------------------------------------------------


def category_values(datasets: list[ErddapDataset], attribute: str) -> list[str]:
    """The values of one category, as ``Erddap.categoryInfo(attribute)`` lists them.

    Every value any dataset has, sorted ignoring case. They are already file-name
    safe and lower case (``LoadDatasets.categorizeGlobalAtts`` and
    ``categorizeVariableAtts``), and ``_null`` stands for a missing attribute.
    """
    found: set[str] = set()
    for ed in datasets:
        found |= categories(ed).get(attribute, set())
    return sorted(found)


def category_datasets(
    datasets: list[ErddapDataset],
    attribute: str,
    value: str,
) -> list[ErddapDataset]:
    """The datasets with ``value`` in ``attribute``, as ``Erddap.categoryInfo(attr, value)``.

    ERDDAP then sorts them by title (``Erddap.sortByTitle``) before paging.
    """
    return by_title([ed for ed in datasets if value in categories(ed).get(attribute, set())])


def category_table(
    kind: str,
    names: list[str],
    base: str,
    ext: str,
    per_page: int,
) -> tuple[list[str], list[list[str]]]:
    """A table of options, each with the URL that opens it.

    ``Erddap.categorizeOptionsTable`` (columns ``Categorize`` and ``URL``, one row
    per attribute) and ``Erddap.sendCategoryPftOptionsTable`` (``Category`` and
    ``URL``, one row per value). The URLs carry ``page=1&itemsPerPage=N``, as
    ERDDAP's ``EDStatic.passThroughPIppQueryPage1`` writes them. ``base`` is the
    URL up to the option: ``{root}/categorize`` or ``{root}/categorize/{attribute}``.
    """
    query = f"page=1&itemsPerPage={per_page}"
    rows = [[name, f"{base}/{name}/index.{ext}?{query}"] for name in names]
    return [kind, "URL"], rows
