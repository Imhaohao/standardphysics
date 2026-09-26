"""The customer route for a scan: a suggestion to start from, and the one the owner confirms."""

from __future__ import annotations

import uuid

from standardphysics_contracts import Scenario

from . import repository as repo
from .db import Database
from .errors import ApiProblem
from .scenario import suggest_path, suggest_scenario
from .worker import ASSESS, Worker


def suggestion(database: Database, scan_id: uuid.UUID, destinations: list[str] | None = None) -> Scenario:
    with database.connect() as connection:
        if not repo.scan_exists(connection, scan_id):
            raise ApiProblem(404, "no scan")
        row = repo.get_revision(connection, scan_id)
    if row is None:
        raise ApiProblem(404, "not ready")
    graph = repo.graph_of(row)
    return suggest_scenario(graph) if destinations is None else suggest_path(graph, destinations)


def confirm(database: Database, worker: Worker, scan_id: uuid.UUID, scenario: Scenario) -> Scenario:
    with database.transaction() as connection:
        if not repo.scan_exists(connection, scan_id):
            raise ApiProblem(404, "no scan")
        row = repo.get_revision(connection, scan_id)
        if row is None:
            raise ApiProblem(409, "the shop is still being measured")
        repo.save_scenario(connection, scan_id, scenario)
        repo.set_state(connection, scan_id, "checking")
        repo.queue_job_again(connection, scan_id, ASSESS, row["revision"])
    worker.wake()
    return scenario
