"""Upload a captured scan directory to a running API.

    python scripts/import_scan.py datasets/phone/test1
    python scripts/import_scan.py datasets/phone/* --api http://127.0.0.1:8787

Goes through the same endpoints the phone uses, so what lands in the workspace
came the same way a real capture does. Every directory needs the `scan.json`
manifest the app writes, which already names each file, its kind, its artifact
id and its checksum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

DEFAULT_API = "http://127.0.0.1:8787"


def post(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or b"{}")


def put_artifact(api: str, scan_id: str, entry: dict, source: pathlib.Path) -> None:
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(f"{source.name} does not match its recorded checksum")

    request = urllib.request.Request(
        f"{api}/api/scans/{scan_id}/artifacts/{entry['artifact_id']}",
        data=data,
        method="PUT",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Kind": entry["kind"],
            "X-Checksum-SHA256": digest,
        },
    )
    urllib.request.urlopen(request).close()


def import_scan(directory: pathlib.Path, api: str) -> str:
    manifest = json.loads((directory / "scan.json").read_text())
    created = post(
        f"{api}/api/scans",
        {
            "name": manifest["name"],
            "device_model": manifest["device_model"],
            "duration_seconds": manifest["duration_seconds"],
        },
    )
    scan_id = created["id"]

    for entry in manifest["files"]:
        source = directory / entry["file"]
        if not source.exists():
            print(f"  {entry['file']}: missing, skipped")
            continue
        put_artifact(api, scan_id, entry, source)
        print(f"  {entry['file']}: {entry['bytes']:,} bytes")

    post(f"{api}/api/scans/{scan_id}/complete", {})
    return scan_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=pathlib.Path)
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()

    for directory in args.directories:
        if not (directory / "scan.json").exists():
            print(f"{directory}: no scan.json, skipped")
            continue
        print(f"{directory.name}:")
        try:
            scan_id = import_scan(directory, args.api)
        except urllib.error.HTTPError as error:
            print(f"  failed: {error.code} {error.read().decode()[:200]}")
            return 1
        print(f"  queued as {scan_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
