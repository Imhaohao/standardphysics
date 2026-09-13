"""The sample shop, entered into the pipeline just after ingest.

It carries the lawsuit variant of the fixture shop (the register on the 47 in
counter, as in Whitaker v. T Rock Inc.) with its human labels, its scenario and
the committed `shop_lawsuit.glb`, so a clean clone has a shop to open without Blender
or a key. From assess onward it takes the same path as a real scan.
"""

from __future__ import annotations

import pathlib
import shutil

from standardphysics_contracts import CreateScanRequest
from standardphysics_fixtures import build_lawsuit_graph, build_lawsuit_scenario

from . import repository as repo
from .db import Database
from .store import ArtifactStore
from .worker import ASSESS

SAMPLE_NAME = "Sample boba shop"
FIXTURE_GLB = pathlib.Path(__import__("standardphysics_fixtures").__file__).parent / "data" / "shop_lawsuit.glb"


def seed_sample_shop(database: Database, store: ArtifactStore) -> bool:
    graph = build_lawsuit_graph()
    with database.transaction() as connection:
        if repo.scan_exists(connection, graph.scan_id):
            return False
        request = CreateScanRequest(name=SAMPLE_NAME, device_model="Sample", duration_seconds=0.0)
        repo.insert_scan(connection, request, scan_id=graph.scan_id, state="checking")
        glb = store.scan_dir(graph.scan_id) / "revisions" / "0" / "scene.glb"
        glb.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_GLB, glb)
        repo.save_revision(connection, graph, source="sample", glb_path=str(glb))
        repo.save_scenario(connection, graph.scan_id, build_lawsuit_scenario())
        repo.enqueue_job(connection, graph.scan_id, ASSESS, graph.revision)
    return True
