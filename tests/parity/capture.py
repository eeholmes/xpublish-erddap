"""Capture golden responses from real ERDDAP servers (needs the network).

Usage, from the repository root::

    python tests/parity/capture.py              # every case
    python tests/parity/capture.py etopo5       # cases whose datasetID matches
    python tests/parity/capture.py --out DIR --compare-to tests/parity/golden

For each case in ``cases.py`` this opens the dataset lazily through the real
server's own griddap OPeNDAP URL, saves a snapshot of it (axes, metadata, and
only the data blocks the requests read), and saves the real server's response
to every request, with a ``manifest.json`` describing them.

By default this overwrites the committed golden files. The scheduled CI job
instead captures into a scratch directory, runs the parity tests against that
(``PARITY_GOLDEN=DIR``), and uses ``--compare-to`` to report how the real
servers have drifted from the committed copies. A raw ``git diff`` is not
useful for that: every response carries a request timestamp, and live
datasets gain time steps.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib import parse

import httpx
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parity.cases import CASES, Case  # noqa: E402
from parity.compare import comparable, ext_of  # noqa: E402
from parity.snapshot import block_bounds, write_snapshot  # noqa: E402
from xpublish_erddap.constraints import (  # noqa: E402
    ConstraintError,
    parse_griddap_query,
)

GOLDEN = Path(__file__).parent / "golden"
SNAPSHOT = "snapshot.nc"
MANIFEST = "manifest.json"
HTTP_OK = 200


def data_blocks(case: Case, ds: xr.Dataset) -> list:
    """The ``(variable, bounds)`` blocks the case's requests will read."""
    axes = {d: ds[d].values for d in ds.dims}
    blocks = []
    for path in case.requests():
        if "?" not in path or ext_of(path) == "dds":
            continue
        query = parse.unquote_plus(path.split("?", 1)[1])
        try:
            parsed = parse_griddap_query(query, axes, list(ds.dims), list(ds.data_vars))
        except ConstraintError:
            continue  # our parser cannot read it yet; the test will say so
        wanted = [v for v in parsed.variables if v in ds.data_vars]
        for name in wanted:
            dims = ds[name].dims
            bounds = {
                d: (parsed.selections[d].start, parsed.selections[d].stop) for d in dims
            }
            block = (name, block_bounds(bounds, ds.sizes))
            if block not in blocks:
                blocks.append(block)
    return blocks


def capture(case: Case, client: httpx.Client, root: Path) -> None:
    """Record one case's snapshot and responses under ``root``."""
    out = root / case.slug
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        old.unlink()

    print(f"== {case.slug}")
    ds = xr.open_dataset(f"{case.server}/griddap/{case.dataset_id}")
    blocks = data_blocks(case, ds)
    write_snapshot(ds, blocks, out / SNAPSHOT)
    print(f"   snapshot: {len(blocks)} block(s)")

    version = client.get(f"{case.server}/version").text.strip()
    entries = []
    for i, path in enumerate(case.requests()):
        resp = client.get(f"{case.server}/{path}")
        ok = resp.status_code == HTTP_OK
        name = f"{i:02d}.{ext_of(path)}" if ok else f"{i:02d}.error"
        (out / name).write_bytes(resp.content)
        entries.append(
            {
                "path": path,
                "file": name,
                "status": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
            },
        )
        print(f"   {resp.status_code} {path}")

    manifest = {
        "server": case.server,
        "dataset_id": case.dataset_id,
        "erddap_version": version,
        "captured": datetime.now(UTC).strftime("%Y-%m-%d"),
        "requests": entries,
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")


def drift(case: Case, new_root: Path, old_root: Path) -> list[str]:
    """Requests whose normalised response differs between two captures."""
    old_path = old_root / case.slug / MANIFEST
    if not old_path.exists():
        return [f"{case.slug}: no committed capture"]
    old = {e["path"]: e for e in json.loads(old_path.read_text())["requests"]}
    new = json.loads((new_root / case.slug / MANIFEST).read_text())["requests"]
    changed = []
    for entry in new:
        before = old.get(entry["path"])
        if before is None:
            changed.append(f"{entry['path']}: new request")
            continue
        if (before["status"], before["content_type"]) != (
            entry["status"],
            entry["content_type"],
        ):
            changed.append(f"{entry['path']}: status or content type")
            continue
        if entry["status"] != HTTP_OK:
            continue
        ext = ext_of(entry["path"])
        before_body = (old_root / case.slug / before["file"]).read_bytes()
        after_body = (new_root / case.slug / entry["file"]).read_bytes()
        a = comparable(before_body, ext, case.server)
        b = comparable(after_body, ext, case.server)
        if a != b:
            changed.append(f"{entry['path']}: body")
    return changed


def main(argv: list[str] | None = None) -> int:
    """Capture the selected cases; return 0 (drift is reported, not fatal)."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("patterns", nargs="*", help="datasetID substrings")
    parser.add_argument("--out", type=Path, default=GOLDEN)
    parser.add_argument("--compare-to", type=Path, default=None)
    args = parser.parse_args(argv)

    cases = [
        c
        for c in CASES
        if not args.patterns or any(p in c.dataset_id for p in args.patterns)
    ]
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for case in cases:
            capture(case, client, args.out)

    if args.compare_to is not None:
        print("\n== drift from", args.compare_to)
        for case in cases:
            changed = drift(case, args.out, args.compare_to)
            print(f"-- {case.slug}: {len(changed) or 'no'} change(s)")
            for line in changed:
                print(f"   {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
