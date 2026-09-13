"""One background thread that runs queued jobs in order.

Run one API process per database. Jobs are claimed atomically, and at startup
every job left running is queued again, on the assumption that the process that
claimed it has stopped. A second process on the same database would rerun the
first process's jobs.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid

from . import repository as repo
from .db import Database
from .stages import Stages
from .store import ArtifactStore

log = logging.getLogger(__name__)

PROCESS, ASSESS, DISPLAY = "process", "assess", "display"


class Worker:
    def __init__(self, database: Database, store: ArtifactStore, stages: Stages):
        self.database, self.store, self.stages = database, store, stages
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self.database.transaction() as connection:
            repo.requeue_interrupted_jobs(connection)
        self._thread = threading.Thread(target=self._loop, name="standardphysics-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        self._wake.set()

    def drain(self) -> None:
        """Run every queued job on the calling thread. Tests use this."""
        while self.run_once():
            pass

    def run_once(self) -> bool:
        with self.database.transaction() as connection:
            job = repo.claim_job(connection)
        if job is None:
            return False
        error = self._run(job)
        with self.database.transaction() as connection:
            repo.finish_job(connection, job["id"], error)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._wake.wait(timeout=2.0)
                self._wake.clear()

    def _run(self, job) -> str | None:
        scan_id, revision = uuid.UUID(job["scan_id"]), job["revision"]
        handler = {PROCESS: self._process, ASSESS: self._assess, DISPLAY: self._display}[job["kind"]]
        try:
            handler(scan_id, revision)
            return None
        except Exception as exc:
            log.error("job %s %s failed:\n%s", job["kind"], scan_id, traceback.format_exc())
            if job["kind"] != DISPLAY:
                with self.database.transaction() as connection:
                    repo.set_state(connection, scan_id, "failed")
            return f"{type(exc).__name__}: {exc}"

    def _process(self, scan_id: uuid.UUID, revision: int) -> None:
        with self.database.connect() as connection:
            room_json = repo.artifact_of_kind(connection, scan_id, "room_json")
        graph = self.stages.ingest(self.store.artifact_path(scan_id, room_json.id), scan_id)
        with self.database.transaction() as connection:
            repo.save_revision(connection, graph, source="ingest")
        self._assess(scan_id, graph.revision)

    def _assess(self, scan_id: uuid.UUID, revision: int) -> None:
        with self.database.transaction() as connection:
            repo.set_state(connection, scan_id, "checking")
            graph = repo.graph_of(repo.get_revision(connection, scan_id, revision))
            scenario = repo.get_scenario(connection, scan_id)
        if scenario is not None:
            assessment = self.stages.assess(graph, scenario, pass_number=revision + 1)
            with self.database.transaction() as connection:
                repo.save_assessment(connection, assessment)
        with self.database.transaction() as connection:
            repo.set_state(connection, scan_id, "ready")
            repo.enqueue_job(connection, scan_id, DISPLAY, revision)
        self.wake()

    def _display(self, scan_id: uuid.UUID, revision: int) -> None:
        with self.database.connect() as connection:
            graph = repo.graph_of(repo.get_revision(connection, scan_id, revision))
            has_glb = repo.base_glb_path(connection, scan_id) is not None
            assessment = repo.assessment_for_revision(connection, scan_id, revision)
            usdz = repo.artifact_of_kind(connection, scan_id, "room_usdz")
            mapping = repo.artifact_of_kind(connection, scan_id, "room_metadata")
        revision_dir = self.store.scan_dir(scan_id) / "revisions" / str(revision)
        if not has_glb:
            self._store_geometry(scan_id, graph, revision_dir, usdz, mapping)
        if assessment is not None:
            rendered = self.stages.renders(
                graph, assessment, revision_dir / "renders",
                lambda finding_id: f"/api/scans/{scan_id}/renders/{finding_id}.png",
            )
            with self.database.transaction() as connection:
                repo.save_assessment(connection, rendered)

    def _store_geometry(self, scan_id, graph, revision_dir, usdz, mapping) -> None:
        inputs = revision_dir / "inputs"
        usdz_path = self._named_input(scan_id, usdz, inputs, "room.usdz")
        mapping_path = self._named_input(scan_id, mapping, inputs, self._mapping_name(scan_id, mapping))
        glb = self.stages.geometry(graph, revision_dir / "scene.glb", usdz_path, mapping_path)
        if glb is not None:
            with self.database.transaction() as connection:
                repo.set_glb_path(connection, scan_id, graph.revision, str(glb))

    def _named_input(self, scan_id, artifact, directory, name):
        """Blender's USD importer reads the file extension, and uploads are stored by artifact ID."""
        if artifact is None:
            return None
        directory.mkdir(parents=True, exist_ok=True)
        link = directory / name
        link.unlink(missing_ok=True)
        link.symlink_to(self.store.artifact_path(scan_id, artifact.id))
        return link

    def _mapping_name(self, scan_id, mapping) -> str:
        if mapping is None:
            return "room.metadata"
        head = self.store.artifact_path(scan_id, mapping.id).read_bytes()[:8]
        return "room.metadata.plist" if head.startswith(b"bplist") else "room.metadata.json"
