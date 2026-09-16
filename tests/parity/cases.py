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
    ),
]
