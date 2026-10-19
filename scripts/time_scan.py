"""Reprocess one stored scan and print how long every job took.

Runs the real worker on a copy of a data directory, so the original is never
touched. The copy lives in --work and is kept, with the detection cache the run
fills, so later runs read the photos' answers from it rather than paying for
them again. --fresh starts the copy over with an empty cache. --job reruns one
kind of job on a revision the copy already has, such as the texture bake.

    python scripts/time_scan.py --data <data_dir> --work <copy> --scan <uuid> [--fresh] [--job texture --revision 2]
    [--profile out.prof]
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "api"))


def _prepared(source: pathlib.Path, work: pathlib.Path, scan_id: uuid.UUID, fresh: bool) -> pathlib.Path:
    if fresh and work.exists():
        shutil.rmtree(work)
    if not work.exists():
        shutil.copytree(source, work, symlinks=True)
        shutil.rmtree(work / "scans" / str(scan_id) / "detections", ignore_errors=True)
    return work


def _finished_since(
    database_path: pathlib.Path, scan_id: uuid.UUID, started: datetime
) -> list[tuple[str, int, datetime]]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT j.kind, j.revision, a.recorded_at FROM job_attempts a JOIN jobs j ON j.id = a.job_id"
            " WHERE j.scan_id = ? ORDER BY a.recorded_at",
            (str(scan_id),),
        ).fetchall()
    finished = [(kind, revision, datetime.fromisoformat(at)) for kind, revision, at in rows]
    return [row for row in finished if row[2] >= started]


def _job_seconds(finished: list[tuple[str, int, datetime]], started: datetime) -> list[dict]:
    """Each job's share of the run, taking the jobs as one after another, as drain runs them."""
    out, previous = [], started
    for kind, revision, at in finished:
        out.append({"kind": kind, "revision": revision, "seconds": round((at - previous).total_seconds(), 1)})
        previous = at
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=pathlib.Path, required=True)
    parser.add_argument("--work", type=pathlib.Path, required=True)
    parser.add_argument("--scan", type=uuid.UUID, required=True)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--job", default="process")
    parser.add_argument("--revision", type=int, default=0)
    parser.add_argument("--profile", type=pathlib.Path)
    args = parser.parse_args()

    os.environ["SP_DATA_DIR"] = str(_prepared(args.data, args.work, args.scan, args.fresh))

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
    with database.transaction() as connection:
        repository_jobs.queue_job_again(connection, args.scan, args.job, args.revision)

    started_at = datetime.now().astimezone()
    started = time.perf_counter()
    profile = cProfile.Profile() if args.profile else None
    if profile:
        profile.enable()
    worker.drain()
    if profile:
        profile.disable()
        profile.dump_stats(args.profile)
    wall = time.perf_counter() - started

    finished = _finished_since(settings.database_path, args.scan, started_at)
    print(json.dumps({"wall_seconds": round(wall, 1), "jobs": _job_seconds(finished, started_at)}, indent=2))


if __name__ == "__main__":
    main()
