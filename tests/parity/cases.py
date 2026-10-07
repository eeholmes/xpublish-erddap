"""Reference datasets on real ERDDAP servers, and the requests to compare.

Requests are paths relative to the server's ``/erddap/`` root, with ``{id}``
standing for the datasetID. They come from what users actually run: the
CoastWatch satellite-course tutorials (hand-built ``.nc`` URLs with date-only
times and off-grid values), the erddapy griddap example (strides, a 0-360
bounding box), and the calls erddapy and rerddap make on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Metadata requests every dataset gets.
METADATA = [
    "griddap/{id}.dds",
    "griddap/{id}.das",
    "griddap/{id}.ncml",
    "info/{id}/index.csv",
    "info/{id}/index.json",
]

#: File types a data request is compared in.
DATA_TYPES = ["csv", "csvp", "csv0", "json", "nc"]


@dataclass(frozen=True)
class Case:
    """One dataset on one real ERDDAP server."""

    server: str
    dataset_id: str
    #: Data queries (without the fileType), each compared in DATA_TYPES.
    queries: list[str] = field(default_factory=list)
    #: Extra full requests, compared as-is (e.g. axis-only, dds with a query).
    extra: list[str] = field(default_factory=list)
    #: Server-wide requests (search). The real answer lists the whole
    #: server's catalog, so only the status and whether this dataset is
    #: listed are compared.
    catalog: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """Directory name for this case's golden files."""
        host = self.server.split("//", 1)[1].split("/", 1)[0]
        return f"{host}__{self.dataset_id}"

    def requests(self) -> list[str]:
        """Every request path for this case, ``{id}`` filled in."""
        paths = list(METADATA)
        for query in self.queries:
            paths.extend(f"griddap/{{id}}.{ext}?{query}" for ext in DATA_TYPES)
        paths.extend(self.extra)
        return [p.replace("{id}", self.dataset_id) for p in paths]


#: What erddapy 3.3 sends for a griddap search: every advanced-search field,
#: unused ones as ``(ANY)`` or empty. ``searchFor`` is appended when given.
ERDDAPY_SEARCH = (
    "search/advanced.csv?page=1&itemsPerPage=1000000&protocol=griddap"
    "&cdm_data_type=(ANY)&institution=(ANY)&ioos_category=(ANY)&keywords=(ANY)"
    "&long_name=(ANY)&standard_name=(ANY)&variableName=(ANY)&minLon=(ANY)"
    "&maxLon=(ANY)&minLat=(ANY)&maxLat=(ANY)&minTime=&maxTime="
)


#: An advanced search for griddap datasets, to add one constraint to.
ADVANCED = "search/advanced.csv?page=1&itemsPerPage=1000&protocol=griddap"

OCEANWATCH = "https://oceanwatch.pifsc.noaa.gov/erddap"
IOOS = "https://erddap.ioos.us/erddap"

CASES = [
    # The dataset the CoastWatch tutorials use. Deprecated upstream, but it is
    # what those notebooks request. Ascending latitude, 0-360 longitude,
    # monthly times stamped on the 1st at 12:00.
    Case(
        OCEANWATCH,
        "CRW_sst_v1_0_monthly",
        queries=[
            # Python tutorial 3: date-only times, off-grid values
            "analysed_sst[(2019-01-15):1:(2019-02-15)]"
            "[(19.2345832):1:(19.3)][(177.84422):1:(177.9)]",
            # R/Python tutorial 1 shape, with a stride, kept small
            "analysed_sst[(2018-01-01T12:00:00Z):1:(2018-02-01T12:00:00Z)]"
            "[(17):2:(17.2)][(195):3:(195.3)]",
            # reversed latitude range on an ascending axis
            "analysed_sst[(2019-01-15)][(19.3):1:(19.2)][(177.84):1:(177.9)]",
            # last, and last-N as an index
            "analysed_sst[(last)][(0.0)][(180.0)]",
            "analysed_sst[last-1:last][100][200]",
        ],
        extra=[
            "griddap/{id}.csvp?time[(last)]",
            "griddap/{id}.csvp?latitude[0:1:2]",
            "griddap/{id}.csvp?time",
            "griddap/{id}.csvp?latitude[(19.3):1:(19.2)]",
            "griddap/{id}.dds?analysed_sst[0:1:1][0:1:2][0:1:3]",
            # axis-only .nc holds just the axes (never the data)
            "griddap/{id}.nc?time[(last)]",
            "griddap/{id}.nc?time[(last)],latitude[0:1:1]",
            # unknown fileTypes are refused
            "griddap/{id}.foo",
            "info/{id}/index.foo",
        ],
    ),
    # Its current replacement: descending latitude, times stamped on the last
    # day of each month at 12:00.
    Case(
        OCEANWATCH,
        "CRW_sst_v3_1_monthly",
        queries=[
            # tutorial-style ascending range on a descending axis
            "sea_surface_temperature[(2019-01-15):1:(2019-02-15)]"
            "[(19.2345832):1:(19.3)][(177.84422):1:(177.9)]",
            # the same range in the axis's own (descending) order
            "sea_surface_temperature[(2019-01-15)][(19.3):1:(19.2)][(177.84):1:(177.9)]",
        ],
        extra=[
            "griddap/{id}.csvp?latitude[(19.2):1:(19.3)]",
            "griddap/{id}.csvp?latitude[(19.3):1:(19.2)]",
        ],
    ),
    # The erddapy griddap example: no time axis, float64 axes.
    Case(
        IOOS,
        "etopo5_EDDGridCopy",
        queries=[
            # the erddapy example's step 10 and off-grid 0-360 bounds, on a
            # smaller box than its (-60.533, 0.033) x (290.908, 340.365)
            "ROSE[(-5.533):10:(0.033)][(330.908):10:(340.365)]",
            "ROSE[(-0.5):1:(0.0)][(359.8):1:(359.9166666666667)]",
        ],
        # This server has one griddap dataset, so a search that should list
        # every dataset must list this one.
        catalog=[
            "search/index.csv?searchFor=etopo5",
            "search/index.csv?searchFor=zzznope",
            # "all" on its own means every dataset, in any case (#19) ...
            "search/index.csv?searchFor=all",
            "search/index.json?searchFor=all",
            "search/index.csv?searchFor=+ALL+",
            "search/advanced.csv?searchFor=all",
            # ... while no searchFor at all is refused
            "search/index.csv?searchFor=",
            "search/index.csv",
            "search/advanced.csv?searchFor=",
            "search/advanced.csv",
            # erddapy's own search URLs, with and without search_for
            ERDDAPY_SEARCH,
            ERDDAPY_SEARCH + "&searchFor=all",
            ERDDAPY_SEARCH.replace("protocol=griddap", "protocol=(ANY)"),
            # The dataset table itself (#27): columns and this dataset's row,
            # in csv and json, from the catalog and from search.
            "griddap/index.csv?page=1&itemsPerPage=1000",
            "griddap/index.json?page=1&itemsPerPage=1000",
            "info/index.csv?page=1&itemsPerPage=1000",
            "search/index.json?searchFor=etopo5",
            # searchFor as ERDDAP's original engine reads it: every line of a
            # dataset's search text starts with "all", phrases are matched
            # whole, and a leading "-" excludes.
            "search/index.csv?searchFor=all+etopo5",
            "search/index.csv?searchFor=all+zzznope",
            'search/index.csv?searchFor="global+surface+relief"',
            'search/index.csv?searchFor="surface+global"',
            "search/index.csv?searchFor=etopo5+-relief",
            "search/index.csv?searchFor=etopo5+-zzznope",
            # Advanced search's constraints (#4). Bounds: kept unless wholly
            # outside; min > max is refused; no time axis fails a time bound.
            *[
                ADVANCED + constraint
                for constraint in [
                    "&minLon=0&maxLon=10",
                    "&minLon=10&maxLon=0",
                    "&minLat=95&maxLat=100",
                    "&minTime=2000-01-01",
                    # categories: cleaned-up values, matched ignoring case;
                    # a value no dataset has is refused
                    "&institution=noaa_marine_geology_and_geophysics_mgg_",
                    "&institution=nonsense",
                    "&variableName=ROSE",
                    "&long_name=relief_of_the_surface_of_the_earth",
                    "&standard_name=altitude",
                    "&ioos_category=bathymetry",
                    "&ioos_category=temperature",
                    "&cdm_data_type=grid",
                    "&keywords=topography",
                ]
            ],
            ADVANCED.replace("protocol=griddap", "protocol=wcs"),
            # no tabledap here; the real server has some, so ask for etopo5
            ADVANCED.replace("protocol=griddap", "protocol=tabledap") + "&searchFor=etopo5",
        ],
    ),
]
