"""Uploaded bytes on the local filesystem, addressed by validated IDs only.

A path is always built from a scan UUID and an artifact ID that passed
`ARTIFACT_ID`, never from anything else a client sends, and the resolved path
must stay under the root.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import tempfile
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class InvalidArtifactId(ValueError):
    pass


class ArtifactTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class StagedUpload:
    temp_path: pathlib.Path
    sha256: str
    bytes: int


class ArtifactStore:
    def __init__(self, root: pathlib.Path, max_bytes: int):
        self.root = root.resolve()
        self.max_bytes = max_bytes

    def artifact_path(self, scan_id: uuid.UUID, artifact_id: str) -> pathlib.Path:
        if not ARTIFACT_ID.fullmatch(artifact_id):
            raise InvalidArtifactId(artifact_id)
        path = (self.root / "scans" / str(scan_id) / "artifacts" / artifact_id).resolve()
        if not path.is_relative_to(self.root):
            raise InvalidArtifactId(artifact_id)
        return path

    def scan_dir(self, scan_id: uuid.UUID) -> pathlib.Path:
        return self.root / "scans" / str(scan_id)

    async def stage(self, scan_id: uuid.UUID, chunks: AsyncIterator[bytes]) -> StagedUpload:
        """Stream a body to a temp file beside its destination while hashing it."""
        directory = self.scan_dir(scan_id) / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        handle = tempfile.NamedTemporaryFile(dir=directory, prefix=".upload-", delete=False)
        try:
            with handle:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ArtifactTooLarge(size)
                    digest.update(chunk)
                    handle.write(chunk)
        except BaseException:
            pathlib.Path(handle.name).unlink(missing_ok=True)
            raise
        return StagedUpload(pathlib.Path(handle.name), digest.hexdigest(), size)

    @staticmethod
    def commit(staged: StagedUpload, destination: pathlib.Path) -> None:
        os.replace(staged.temp_path, destination)

    @staticmethod
    def discard(staged: StagedUpload) -> None:
        staged.temp_path.unlink(missing_ok=True)
