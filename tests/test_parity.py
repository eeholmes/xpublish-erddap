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
from parity.compare import comparable, ext_of, media_type
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
KNOWN: list[tuple[str, str]] = []

#: The same, for media-type differences.
KNOWN_MEDIA: list[tuple[str, str]] = [
    (
        r"^etopo5_EDDGridCopy griddap/\S*\.das$",
        "ERDDAP 2.31 serves .das as text/csv; 2.22 says text/plain. Not copied.",
    ),
]


def _params(*, media: bool = False):
    known = KNOWN_MEDIA if media else KNOWN
    params = []
    for manifest_path in sorted(GOLDEN.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        slug = manifest_path.parent.name
        for entry in manifest["requests"]:
            key = f"{manifest['dataset_id']} {entry['path']}"
            reasons = [why for pattern, why in known if re.search(pattern, key)]
            marks = (
                [pytest.mark.xfail(reason="; ".join(reasons), strict=True)]
                if reasons
                else []
            )
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
        return

    assert ours.status_code == HTTP_OK, ours.text[:500]
    ext = ext_of(entry["path"])
    server = manifest["server"]
    real = (GOLDEN / slug / entry["file"]).read_bytes()
    assert comparable(ours.content, ext, OUR_SERVER) == comparable(real, ext, server)


@pytest.mark.parametrize(("slug", "manifest", "entry"), _params(media=True))
def test_media_type_matches_real_erddap(slug, manifest, entry):
    """Same media type as the real ERDDAP (charset aside)."""
    if entry["status"] != HTTP_OK:
        pytest.skip("ERDDAP returned an error")
    ours = _client(slug, manifest["dataset_id"]).get(f"/erddap/{entry['path']}")
    assert media_type(ours.headers.get("content-type")) == media_type(
        entry["content_type"],
    )
