"""SQLite, one short-lived connection per unit of work.

Connections run in autocommit mode so `transaction` can issue BEGIN IMMEDIATE
itself. That takes the write lock up front, which is what makes finalize and
job claiming safe when two requests arrive together.
"""

from __future__ import annotations

import contextlib
import pathlib
import sqlite3
from collections.abc import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    device_model TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT,
    coverage_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS artifacts (
    scan_id TEXT NOT NULL REFERENCES scans(id),
    id TEXT NOT NULL,
    kind TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (scan_id, id)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    kind TEXT NOT NULL,
    revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (scan_id, kind, revision)
);
CREATE TABLE IF NOT EXISTS revisions (
    scan_id TEXT NOT NULL REFERENCES scans(id),
    revision INTEGER NOT NULL,
    graph_hash TEXT NOT NULL,
    graph_json TEXT NOT NULL,
    source TEXT NOT NULL,
    base_revision INTEGER,
    glb_path TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (scan_id, revision)
);
CREATE TABLE IF NOT EXISTS scenarios (
    scan_id TEXT PRIMARY KEY REFERENCES scans(id),
    scenario_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS simulations (
    scan_id TEXT NOT NULL REFERENCES scans(id),
    revision INTEGER NOT NULL,
    request_json TEXT NOT NULL,
    graph_json TEXT NOT NULL,
    scenario_json TEXT NOT NULL,
    mesh_artifact_id TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    PRIMARY KEY (scan_id, revision)
);
CREATE TABLE IF NOT EXISTS assessments (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    graph_revision INTEGER NOT NULL,
    assessment_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: pathlib.Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
