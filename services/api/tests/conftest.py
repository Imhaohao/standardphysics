import hashlib
import pathlib
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient

from standardphysics_api.app import create_app
from standardphysics_api.settings import Settings
from standardphysics_api.stages import Stages, preview_ledger
from standardphysics_pipeline import blender

REPO = pathlib.Path(__file__).resolve().parents[3]
FIXTURE_DATA = REPO / "packages/fixtures/standardphysics_fixtures/data"
PNG = b"\x89PNG\r\n\x1a\n"


def no_blender_stages(**overrides) -> Stages:
    """Every Lane B and C stage is real except the ones that launch Blender."""

    def export_glb(graph, out: pathlib.Path) -> pathlib.Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_DATA / "shop.glb", out)
        return out

    def usdz_to_glb(usdz, out, mapping):
        raise blender.BlenderError("no Blender in tests")

    def render_finding(graph, locus, out: pathlib.Path) -> pathlib.Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(PNG)
        return out

    options = dict(
        ledger_factory=preview_ledger, export_glb=export_glb,
        usdz_to_glb=usdz_to_glb, render_finding=render_finding,
    )
    return Stages(**{**options, **overrides})


@pytest.fixture
def make_client(tmp_path):
    def build(seed: bool = False, stages: Stages | None = None) -> TestClient:
        settings = Settings(data_dir=tmp_path / "var", seed_sample_shop=seed, max_artifact_bytes=5_000_000)
        return TestClient(create_app(settings, stages or no_blender_stages(), run_worker=False))

    return build


@pytest.fixture
def client(make_client):
    with make_client() as test_client:
        yield test_client


def drain(test_client: TestClient) -> None:
    test_client.app.state.worker.drain()


def create_scan(test_client: TestClient) -> str:
    response = test_client.post(
        "/api/scans", json={"name": "Corner cafe", "device_model": "iPhone17,1", "duration_seconds": 142.5}
    )
    assert response.status_code == 201
    return response.json()["id"]


def put_artifact(test_client, scan_id, artifact_id, body: bytes, kind: str, checksum: str | None = None):
    return test_client.put(
        f"/api/scans/{scan_id}/artifacts/{artifact_id}",
        content=body,
        headers={"X-Checksum-SHA256": checksum or hashlib.sha256(body).hexdigest(), "X-Artifact-Kind": kind},
    )


def unknown_scan() -> str:
    return str(uuid.uuid4())
