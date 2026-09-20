"""Content hashing and run-record validation for the benchmark protocol.

Hashes pin inputs, code, and the evaluator before candidate runs.  They prove
internal consistency only; the same agent that writes them can edit them, so a
read-only reviewer should still re-derive metrics from images independently.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Iterable, Mapping

from .metrics import MetricError


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path | str) -> str:
    with pathlib.Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def canonical_hash(obj: Mapping) -> str:
    """SHA-256 of a canonically serialized JSON object (sorted keys, no trailing newline)."""
    serialized = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_expected_files(paths: Iterable[pathlib.Path | str]) -> None:
    missing = [str(path) for path in paths if not pathlib.Path(path).is_file()]
    if missing:
        raise MetricError(f"missing expected artifacts: {', '.join(missing)}")


def validate_view_list(views: Iterable[Mapping], identifier_key: str = "file_path") -> None:
    """A view list must be non-empty, unique, and each entry must carry an id."""
    entries = list(views)
    if not entries:
        raise MetricError("view list is empty")
    identifiers = []
    for entry in entries:
        if not isinstance(entry, Mapping) or identifier_key not in entry:
            raise MetricError(f"view entry lacks {identifier_key!r}")
        identifiers.append(entry[identifier_key])
    if len(set(identifiers)) != len(identifiers):
        raise MetricError("view list contains duplicate entries")
