"""Compare our responses with golden responses captured from real ERDDAPs.

See ``tests/parity/__init__.py``. Runs offline from committed golden files;
``tests/parity/capture.py`` refreshes them.

Known differences are listed in ``KNOWN`` and marked ``xfail(strict=True)``:
fixing one makes its test pass unexpectedly, which fails the run until the
entry is removed, so the list can only shrink.
"""

from __future__ import annotations

import json
import os
import re
from functools import cache
from pathlib import Path

import pytest
import xpublish
from fastapi.testclient import TestClient
from parity.compare import comparable, dataset_table, ext_of, lists, media_type, normalise_text
from parity.snapshot import load_snapshot

from xpublish_erddap import ErddapPlugin

#: Committed captures; the scheduled CI job points this at a fresh capture.
GOLDEN = Path(
    os.environ.get("PARITY_GOLDEN", Path(__file__).parent / "parity" / "golden"),
)
HTTP_OK = 200
HTTP_ERROR = 400
#: The base URL TestClient requests go to.
OUR_SERVER = "http://testserver/erddap"

#: Known differences: (regex, reason). A regex is searched in
#: "<datasetID> <request path>"; every matching reason applies.
KNOWN: list[tuple[str, str]] = [
    (
        r"^dhw_5km griddap/dhw_5km\.dods\?",
        "ERDDAP's .dods (DodsFiles.saveAsDODS) has no case for unsigned types: it sends "
        "the array's length, logs 'unsupported source data type' and stops, a truncated "
        "200. Ours sends the data, as Byte (#2).",
    ),
]

#: The same, for media-type differences.
KNOWN_MEDIA: list[tuple[str, str]] = [
    (
        r"^(etopo5_EDDGridCopy|jplMURSST41|dhw_5km|noaac\w+) griddap/\S*\.das$",
        "ERDDAP 2.29 and 2.31 serve .das as text/csv; 2.22 says text/plain. Not copied.",
    ),
]


def _params(*, media: bool = False):
    known = KNOWN_MEDIA if media else KNOWN
    params = []
    for manifest_path in sorted(GOLDEN.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        slug = manifest_path.parent.name
        for entry in manifest["requests"]:
            if media and entry["status"] != HTTP_OK:
                # An error response has no media type worth comparing; leave
                # it out here rather than skip it at run time (#112).
                continue
            key = f"{manifest['dataset_id']} {entry['path']}"
            reasons = [why for pattern, why in known if re.search(pattern, key)]
            marks = [pytest.mark.xfail(reason="; ".join(reasons), strict=True)] if reasons else []
            params.append(
                pytest.param(
                    slug,
                    manifest,
                    entry,
                    id=f"{manifest['dataset_id']}:{entry['path'].split('/', 1)[1]}",
                    marks=marks,
                ),
            )
    return params


@cache
def _client(slug: str, dataset_id: str) -> TestClient:
    ds = load_snapshot(GOLDEN / slug / "snapshot.nc")
    rest = xpublish.Rest({dataset_id: ds}, plugins={"erddap": ErddapPlugin()})
    return TestClient(rest.app)


@pytest.mark.parametrize(("slug", "manifest", "entry"), _params())
def test_matches_real_erddap(slug, manifest, entry):
    """Our response matches what the real ERDDAP returned."""
    client = _client(slug, manifest["dataset_id"])
    ours = client.get(f"/erddap/{entry['path']}")

    if entry["status"] != HTTP_OK:
        # ERDDAP refused; so must we. Neither the body nor the exact code is
        # compared: oceanwatch's proxy turns ERDDAP's query errors into a bare
        # 500, and a bad request should not get a 500 from us.
        assert ours.status_code >= HTTP_ERROR, ours.text[:500]
        # Where the golden is ERDDAP's own error body (not a proxy's page), our
        # body must be the same text (#36).
        real = (GOLDEN / slug / entry["file"]).read_bytes() if "file" in entry else b""
        if real.startswith(b"Error {"):
            server = manifest["server"]
            assert normalise_text(ours.text, (OUR_SERVER, server)) == normalise_text(
                real.decode(),
                server,
            )
        return

    assert ours.status_code == HTTP_OK, ours.text[:500]
    if entry.get("catalog"):
        # A search: the real server lists its whole catalog, so compare whether
        # this dataset is in the result, and the table's header and this
        # dataset's row (#27).
        assert lists(ours.text, manifest["dataset_id"]) == entry["lists_dataset"]
        if "file" in entry:
            ext, server = ext_of(entry["path"]), manifest["server"]
            real = (GOLDEN / slug / entry["file"]).read_bytes()
            dataset_id = manifest["dataset_id"]
            assert dataset_table(ours.content, ext, dataset_id, (OUR_SERVER, server)) == (
                dataset_table(real, ext, dataset_id, server)
            )
        return
    ext = ext_of(entry["path"])
    server = manifest["server"]
    real = (GOLDEN / slug / entry["file"]).read_bytes()
    assert comparable(ours.content, ext, (OUR_SERVER, server)) == comparable(real, ext, server)


@pytest.mark.parametrize(("slug", "manifest", "entry"), _params(media=True))
def test_media_type_matches_real_erddap(slug, manifest, entry):
    """Same media type as the real ERDDAP (charset aside)."""
    ours = _client(slug, manifest["dataset_id"]).get(f"/erddap/{entry['path']}")
    assert media_type(ours.headers.get("content-type")) == media_type(
        entry["content_type"],
    )
