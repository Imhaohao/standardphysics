"""One hash for a layout, so every lane means the same thing by it.

Only the scan and its nodes count. The revision number and the hash of the
graph it came from do not, so two revisions with identical geometry hash equal.
"""

from __future__ import annotations

import hashlib
import json

from .scene import SceneGraph


def graph_hash(graph: SceneGraph) -> str:
    payload = graph.model_dump(mode="json", include={"scan_id", "nodes"})
    payload["nodes"] = sorted(payload["nodes"], key=lambda node: node["id"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
