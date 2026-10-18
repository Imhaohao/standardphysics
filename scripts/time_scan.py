"""Reprocess one stored scan from scratch and print how long every stage took.

Runs the real worker on a copy of a data directory, so the original is never
touched. Process, assess, display and texture run in order on this thread,
and the detection cache is cleared first so the photos are read again.

    SP_BAKE_IN_OWN_PROCESS=0 python scripts/time_scan.py --data <data_dir> --scan <uuid>
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time
import uuid
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "api"))

STAGE_FUNCTIONS = [
    ("standardphysics_api.stages", "Stages", "ingest_with_report"),
    ("standardphysics_api.stages", "Stages", "assess"),
    ("standardphysics_api.stages", "Stages", "geometry"),
    ("standardphysics_api.stages", "Stages", "renders"),
    ("standardphysics_api.stages", "Stages", "bake_textures"),
    ("standardphysics_api.stages", "Stages", "label_scan"),
    ("standardphysics_api.stages", "Stages", "discover_scan_with_report"),
    ("standardphysics_pipeline.discovery.discover", None, "detect_objects"),
    ("standardphysics_pipeline.discovery.discover", None, "segment_surfaces"),
]

totals: dict[str, float] = defaultdict(float)
calls: dict[str, int] = defaultdict(int)


def _timed(name, function):
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            totals[name] += time.perf_counter() - started
            calls[name] += 1

    return wrapper


def _instrument() -> None:
    import importlib

    for module_name, class_name, attribute in STAGE_FUNCTIONS:
        with contextlib.suppress(ImportError, AttributeError):
            module = importlib.import_module(module_name)
            owner = getattr(module, class_name) if class_name else module
            original = getattr(owner, attribute)
            setattr(owner, attribute, _timed(f"{module_name.rsplit('.', 1)[-1]}.{attribute}", original))


def _copy_data(source: pathlib.Path, scan_id: uuid.UUID) -> pathlib.Path:
    target = pathlib.Path(tempfile.mkdtemp(prefix="time-scan-")) / "data"
    shutil.copytree(source, target, symlinks=True)
    shutil.rmtree(target / "scans" / str(scan_id) / "detections", ignore_errors=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=pathlib.Path, required=True)
    parser.add_argument("--scan", type=uuid.UUID, required=True)
    parser.add_argument("--revision", type=int, default=0)
    args = parser.parse_args()

    os.environ["SP_DATA_DIR"] = str(_copy_data(args.data, args.scan))
    _instrument()

    from standardphysics_api import repository_jobs
    from standardphysics_api.db import Database
    from standardphysics_api.settings import Settings
    from standardphysics_api.stages import configured_stages
    from standardphysics_api.store import ArtifactStore
    from standardphysics_api.worker import Worker

    settings = Settings.from_environment()
    database = Database(settings.database_path)
    store = ArtifactStore(settings.data_dir, settings.max_artifact_bytes)
    worker = Worker(database, store, configured_stages(settings), settings)

    job_seconds: list[tuple[str, float, str]] = []
    run_stage = worker.run_stage

    def timed_stage(job):
        started = time.perf_counter()
        try:
            return run_stage(job)
        finally:
            job_seconds.append((job["kind"], time.perf_counter() - started, str(job["revision"])))

    worker.run_stage = timed_stage
    with database.transaction() as connection:
        repository_jobs.queue_job_again(connection, args.scan, "process", args.revision)

    started = time.perf_counter()
    worker.drain()
    wall = time.perf_counter() - started

    print(
        json.dumps(
            {
                "wall_seconds": round(wall, 1),
                "jobs": [{"kind": k, "seconds": round(s, 1), "revision": r} for k, s, r in job_seconds],
                "stages_summed_across_threads": {
                    name: {"seconds": round(totals[name], 1), "calls": calls[name]} for name in totals
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
