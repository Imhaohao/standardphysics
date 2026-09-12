"""The HTTP surface. Upload paths and status codes follow services/api/openapi.json."""

from __future__ import annotations

import contextlib
import logging
import pathlib
import uuid
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from standardphysics_contracts import (
    Artifact,
    ArtifactKind,
    Assessment,
    CreateScanRequest,
    LayoutCheckRequest,
    LayoutCheckResult,
    SaveLayoutRequest,
    Scan,
    ScanList,
    Scenario,
    SceneGraph,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import repository as repo
from .coverage import parse_coverage
from .db import Database
from .errors import ApiProblem
from .layout import check_layout, save_layout
from .seed import seed_sample_shop
from .settings import Settings
from .stages import Stages, preview_ledger
from .store import ArtifactStore, ArtifactTooLarge, InvalidArtifactId
from .worker import PROCESS, Worker

log = logging.getLogger(__name__)


def _problem_response(exc: ApiProblem) -> JSONResponse:
    return JSONResponse(exc.body.model_dump(exclude_none=True), status_code=exc.status)


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def api_problem(_: Request, exc: ApiProblem):
        return _problem_response(exc)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError):
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return _problem_response(ApiProblem(400, "invalid request", need=fields))

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(_: Request, exc: StarletteHTTPException):
        return _problem_response(ApiProblem(exc.status_code, str(exc.detail).lower()))


def create_app(settings: Settings | None = None, stages: Stages | None = None, run_worker: bool = True) -> FastAPI:
    settings = settings or Settings.from_environment()
    if stages is None:
        stages = Stages(ledger_factory=preview_ledger) if settings.preview_unverified_rules else Stages()
    database = Database(settings.database_path)
    store = ArtifactStore(settings.data_dir, settings.max_artifact_bytes)
    worker = Worker(database, store, stages)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.preview_unverified_rules:
            log.warning("SP_PREVIEW_UNVERIFIED_RULES is on: findings come from rules no person has verified")
        if settings.seed_sample_shop:
            seed_sample_shop(database, store)
        if run_worker:
            worker.start()
        yield
        if run_worker:
            worker.stop()

    app = FastAPI(title="Standard Physics API", version="0.1.0", lifespan=lifespan)
    app.state.database, app.state.store, app.state.worker = database, store, worker
    _install_error_handlers(app)
    _install_scan_routes(app, database)
    _install_upload_routes(app, database, store, worker)
    _install_workspace_routes(app, database, store)
    _install_layout_routes(app, database, stages, worker)
    return app


def _scan_or_404(connection, scan_id: uuid.UUID) -> Scan:
    scan = repo.get_scan(connection, scan_id)
    if scan is None:
        raise ApiProblem(404, "no scan")
    return scan


def _install_scan_routes(app: FastAPI, database: Database) -> None:
    @app.post("/api/scans", status_code=201, response_model=Scan)
    def create_scan(body: CreateScanRequest) -> Scan:
        with database.transaction() as connection:
            scan_id = repo.insert_scan(connection, body)
            return repo.get_scan(connection, scan_id)

    @app.get("/api/scans", response_model=ScanList)
    def list_scans() -> ScanList:
        with database.connect() as connection:
            return ScanList(scans=repo.list_scans(connection))

    @app.get("/api/scans/{scan_id}", response_model=Scan)
    def get_scan(scan_id: uuid.UUID) -> Scan:
        with database.connect() as connection:
            return _scan_or_404(connection, scan_id)


def _accept_staged(database, store, scan_id, artifact_id, kind, claimed, staged) -> tuple[int, Artifact]:
    if staged.sha256 != claimed.lower():
        store.discard(staged)
        raise ApiProblem(400, "checksum mismatch")
    with database.transaction() as connection:
        _scan_or_404(connection, scan_id)
        existing = repo.find_artifact(connection, scan_id, artifact_id)
        if existing is not None:
            store.discard(staged)
            if existing.sha256 != staged.sha256:
                raise ApiProblem(409, "artifact already stored with different content")
            return 200, existing
        artifact = Artifact(id=artifact_id, kind=kind, sha256=staged.sha256, bytes=staged.bytes)
        repo.insert_artifact(connection, scan_id, artifact)
        store.commit(staged, store.artifact_path(scan_id, artifact_id))
        return 201, artifact


def _finalize(database: Database, store: ArtifactStore, scan_id: uuid.UUID) -> tuple[Scan, bool]:
    with database.transaction() as connection:
        scan = _scan_or_404(connection, scan_id)
        if scan.state != "uploading":
            return scan, False
        missing = repo.missing_required(scan)
        if missing:
            raise ApiProblem(409, "missing artifacts", need=missing)
        coverage_artifact = next((a for a in scan.artifacts if a.kind == "coverage"), None)
        coverage = (
            parse_coverage(store.artifact_path(scan_id, coverage_artifact.id).read_bytes())
            if coverage_artifact else []
        )
        repo.mark_finalized(connection, scan, coverage)
        repo.enqueue_job(connection, scan_id, PROCESS, 0)
        return repo.get_scan(connection, scan_id), True


def _install_upload_routes(app: FastAPI, database: Database, store: ArtifactStore, worker: Worker) -> None:
    @app.put("/api/scans/{scan_id}/artifacts/{artifact_id}", response_model=Artifact, status_code=201)
    async def upload_artifact(
        scan_id: uuid.UUID,
        artifact_id: str,
        request: Request,
        x_checksum_sha256: Annotated[str, Header()],
        x_artifact_kind: Annotated[ArtifactKind, Header()],
    ):
        with database.connect() as connection:
            _scan_or_404(connection, scan_id)
        try:
            store.artifact_path(scan_id, artifact_id)
            staged = await store.stage(scan_id, request.stream())
        except InvalidArtifactId:
            raise ApiProblem(400, "invalid artifact id") from None
        except ArtifactTooLarge:
            raise ApiProblem(413, "artifact too large") from None
        status, artifact = _accept_staged(
            database, store, scan_id, artifact_id, x_artifact_kind, x_checksum_sha256, staged
        )
        return JSONResponse(artifact.model_dump(mode="json"), status_code=status)

    @app.post("/api/scans/{scan_id}/complete", response_model=Scan)
    def complete(scan_id: uuid.UUID) -> Scan:
        scan, queued = _finalize(database, store, scan_id)
        if queued:
            worker.wake()
        return scan


def _file_or_404(path: str | pathlib.Path | None, media_type: str) -> FileResponse:
    if path is None or not pathlib.Path(path).is_file():
        raise ApiProblem(404, "not ready")
    return FileResponse(path, media_type=media_type)


def _install_workspace_routes(app: FastAPI, database: Database, store: ArtifactStore) -> None:
    @app.get("/api/scans/{scan_id}/scene", response_model=SceneGraph)
    def scene(scan_id: uuid.UUID, revision: int | None = None) -> SceneGraph:
        with database.connect() as connection:
            _scan_or_404(connection, scan_id)
            row = repo.get_revision(connection, scan_id, revision)
        if row is None:
            raise ApiProblem(404, "not ready")
        return repo.graph_of(row)

    @app.get("/api/scans/{scan_id}/scene.glb")
    def scene_glb(scan_id: uuid.UUID) -> FileResponse:
        with database.connect() as connection:
            _scan_or_404(connection, scan_id)
            path = repo.base_glb_path(connection, scan_id)
        return _file_or_404(path, "model/gltf-binary")

    @app.get("/api/scans/{scan_id}/scenario", response_model=Scenario)
    def scenario(scan_id: uuid.UUID) -> Scenario:
        with database.connect() as connection:
            _scan_or_404(connection, scan_id)
            found = repo.get_scenario(connection, scan_id)
        if found is None:
            raise ApiProblem(404, "not ready")
        return found

    @app.get("/api/scans/{scan_id}/assessment", response_model=Assessment)
    def assessment(scan_id: uuid.UUID) -> Assessment:
        with database.connect() as connection:
            _scan_or_404(connection, scan_id)
            found = repo.latest_assessment(connection, scan_id)
        if found is None:
            raise ApiProblem(404, "not ready")
        return found

    @app.get("/api/scans/{scan_id}/renders/{finding_id}.png")
    def render(scan_id: uuid.UUID, finding_id: uuid.UUID) -> FileResponse:
        with database.connect() as connection:
            revision = repo.get_revision(connection, scan_id)
        if revision is None:
            raise ApiProblem(404, "not ready")
        directory = store.scan_dir(scan_id) / "revisions"
        matches = sorted(directory.glob(f"*/renders/{finding_id}.png"))
        return _file_or_404(matches[-1] if matches else None, "image/png")


def _install_layout_routes(app: FastAPI, database: Database, stages: Stages, worker: Worker) -> None:
    @app.post("/api/scans/{scan_id}/layout-checks", response_model=LayoutCheckResult)
    def layout_check(scan_id: uuid.UUID, body: LayoutCheckRequest) -> LayoutCheckResult:
        return check_layout(database, stages, scan_id, body)

    @app.post("/api/scans/{scan_id}/revisions", response_model=SceneGraph, status_code=201)
    def save_revision(scan_id: uuid.UUID, body: SaveLayoutRequest) -> SceneGraph:
        return save_layout(database, worker, scan_id, body)
