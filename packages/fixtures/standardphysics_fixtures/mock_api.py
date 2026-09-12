"""The upload contract, served locally, so Lane A never waits on Lane D.

    python -m standardphysics_fixtures.mock_api

Serves on :8787. Stdlib only, no install required. State is in memory and
artifacts land in a temp directory; restarting forgets everything, which is
what you want while iterating on a client.

Lane D implements the same paths for real. If the two ever disagree, the
OpenAPI document at services/api/openapi.json is the contract, not this file.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8787
STORE = pathlib.Path(tempfile.gettempdir()) / "standardphysics-mock"
SCANS: dict[str, dict] = {}

REQUIRED = {"room_usdz", "room_json"}
"""Finalizing without these fails, the same way the real API will."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path} -> {args[1]}")

    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}

    def do_POST(self) -> None:
        parts = [p for p in self.path.split("/") if p]
        if parts == ["api", "scans"]:
            return self._create_scan()
        if len(parts) == 4 and parts[:2] == ["api", "scans"] and parts[3] == "complete":
            return self._complete(parts[2])
        self._send(404, {"error": "not found"})

    def do_PUT(self) -> None:
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 5 and parts[3] == "artifacts":
            return self._upload(parts[2], parts[4])
        self._send(404, {"error": "not found"})

    def do_GET(self) -> None:
        parts = [p for p in self.path.split("/") if p]
        if parts == ["api", "scans"]:
            return self._send(200, {"scans": list(SCANS.values())})
        if len(parts) == 3 and parts[:2] == ["api", "scans"]:
            scan = SCANS.get(parts[2])
            return self._send(200, scan) if scan else self._send(404, {"error": "no scan"})
        self._send(404, {"error": "not found"})

    def _create_scan(self) -> None:
        body = self._body()
        scan_id = str(uuid.uuid4())
        SCANS[scan_id] = {
            "id": scan_id,
            "name": body.get("name", "Untitled"),
            "created_at": _now(),
            "device_model": body.get("device_model", "unknown"),
            "duration_seconds": body.get("duration_seconds", 0.0),
            "state": "uploading",
            "artifacts": [],
        }
        self._send(201, SCANS[scan_id])

    def _upload(self, scan_id: str, artifact_id: str) -> None:
        scan = SCANS.get(scan_id)
        if not scan:
            return self._send(404, {"error": "no scan"})

        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length) if length else b""
        digest = hashlib.sha256(data).hexdigest()
        claimed = self.headers.get("X-Checksum-SHA256")
        if claimed and claimed != digest:
            return self._send(400, {"error": "checksum mismatch", "computed": digest})

        existing = next(
            (a for a in scan["artifacts"] if a["id"] == artifact_id), None
        )
        if existing:
            return self._send(200, existing)

        STORE.mkdir(parents=True, exist_ok=True)
        path = STORE / scan_id / artifact_id
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

        artifact = {
            "id": artifact_id,
            "kind": self.headers.get("X-Artifact-Kind", "room_json"),
            "sha256": digest,
            "bytes": len(data),
            "stored_path": str(path),
        }
        scan["artifacts"].append(artifact)
        self._send(201, artifact)

    def _complete(self, scan_id: str) -> None:
        scan = SCANS.get(scan_id)
        if not scan:
            return self._send(404, {"error": "no scan"})
        if scan["state"] != "uploading":
            return self._send(200, scan)

        kinds = {a["kind"] for a in scan["artifacts"]}
        if not REQUIRED.issubset(kinds):
            return self._send(
                409,
                {"error": "missing artifacts", "need": sorted(REQUIRED - kinds)},
            )
        scan["state"] = "measuring"
        self._send(200, scan)


def main() -> None:
    print(f"mock API on http://127.0.0.1:{PORT}  artifacts -> {STORE}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
