"""From two videos to a list of changes, with the shared 3D scene they sit in."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import changes as change_records
from .evidence import GONE, KEPT, UNSEEN, DepthLookup, Tolerance, classify, gather
from .export import write_report
from .geometry import Cloud, apply, build_cloud, room_frame
from .landmarks import Landmark, apart_from, find_landmarks, merge_touching, place_phrase, vote_classes
from .matching import MatchRules, pair_moves
from .naming import Embedder, Namer, Segmenter, make_namer
from .pictures import isolated, outlined, sightings
from .regions import Region, RegionRules, find_regions, finish_regions
from .views import AFTER, BEFORE, View, load_views, of_epoch, save_views


@dataclass
class Settings:
    frames_per_video: int = 32
    voxel_m: float = 0.02
    namer: str = "auto"
    fov_deg: float | None = None
    tolerance: Tolerance = field(default_factory=Tolerance)
    regions: RegionRules = field(default_factory=RegionRules)
    matching: MatchRules = field(default_factory=MatchRules)
    reuse_reconstruction: bool = True


@dataclass
class Scene:
    views: list[View]
    cloud: Cloud
    status: np.ndarray
    through: np.ndarray
    agree: np.ndarray


class Timer:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log, self.spent, self._start = log, {}, time.perf_counter()

    def lap(self, stage: str) -> None:
        now = time.perf_counter()
        self.spent[stage] = round(now - self._start, 1)
        self.log(f"{stage}: {self.spent[stage]} s")
        self._start = now


CACHE = Path.home() / ".cache" / "sp-changes" / "reconstructions"


def cache_path(before: Path, after: Path, settings: Settings) -> Path:
    """One cached reconstruction per pair of videos and the settings that shape it."""
    digest = hashlib.sha1()
    for video in (before, after):
        digest.update(Path(video).read_bytes())
    digest.update(f"{settings.frames_per_video}|{settings.fov_deg}".encode())
    return CACHE / f"{digest.hexdigest()[:16]}.npz"


def reconstruct_videos(before: Path, after: Path, settings: Settings, log) -> list[View]:
    cache = cache_path(before, after, settings)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if settings.reuse_reconstruction and cache.exists():
        log(f"reusing {cache}")
        return load_views(cache)
    from .reconstruct import reconstruct
    from .video import sample_frames

    first = sample_frames(before, settings.frames_per_video)
    second = sample_frames(after, settings.frames_per_video)
    log(f"sampled {len(first)} + {len(second)} frames")
    views = reconstruct(first, second, settings.fov_deg)
    save_views(views, cache)
    return views


def to_room(views: list[View], settings: Settings) -> tuple[list[View], Cloud]:
    cloud = build_cloud(views, settings.voxel_m)
    transform = room_frame(views, cloud.points)
    cloud.points = apply(transform, cloud.points)
    return [view.moved_by(transform) for view in views], cloud


def judge(views: list[View], cloud: Cloud, tolerance: Tolerance) -> Scene:
    """Test each recording's points against the other recording's cameras."""
    count = len(cloud)
    status = np.full(count, UNSEEN, dtype=np.uint8)
    through, agree = np.zeros(count, dtype=np.int32), np.zeros(count, dtype=np.int32)
    lookups = {epoch: [DepthLookup.of(view, tolerance) for view in of_epoch(views, epoch)] for epoch in (BEFORE, AFTER)}
    for epoch, other in ((BEFORE, AFTER), (AFTER, BEFORE)):
        mine = cloud.epoch == epoch
        support = gather(cloud.points[mine], lookups[epoch], tolerance).agree
        evidence = gather(cloud.points[mine], lookups[other], tolerance)
        status[mine] = classify(evidence, support)
        through[mine], agree[mine] = evidence.through, evidence.agree
    return Scene(views, cloud, status, through, agree)


def regions_of(scene: Scene, rules: RegionRules) -> tuple[list[Region], list[Region]]:
    found = {}
    for epoch, kind in ((BEFORE, "removed"), (AFTER, "added")):
        ids = np.flatnonzero(scene.cloud.epoch == epoch)
        regions = find_regions(scene.cloud.points[ids], scene.status[ids], kind, epoch, rules)
        for region in regions:
            region.point_ids = ids[region.point_ids]
        found[kind] = finish_regions(regions, scene.cloud.points, rules)
    return found["removed"], found["added"]


def describe_regions(scene: Scene, regions: list[Region], namer: Namer, embedder: Embedder | None) -> None:
    for region in regions:
        points = scene.cloud.points[region.point_ids]
        seen = sightings(points, of_epoch(scene.views, region.epoch))
        if not seen:
            region.names = {"name": "object", "detail": "object", "where": ""}
            continue
        region.names = namer.name(outlined(seen[0], margin=1.2))
        if embedder is not None:
            region.descriptor = embedder.embed([isolated(s) for s in seen[:3]])


def name_landmarks(scene: Scene, namer: Namer, segmenter: Segmenter | None, changed: list[Region]) -> list[Landmark]:
    """Find and name the unchanged furniture of the before video, which the change sentences point to."""
    if segmenter is None:
        return []
    ids = np.flatnonzero(scene.cloud.epoch == BEFORE)
    points = scene.cloud.points[ids]
    views = of_epoch(scene.views, BEFORE)[::2]
    classes = vote_classes(points, views, [segmenter.classes(view.image) for view in views])
    found = find_landmarks(points, scene.status[ids], classes, segmenter.names, ceiling_height(scene))
    found = merge_touching(apart_from(found, points, [region.box for region in changed]), points)
    for landmark in found:
        landmark.point_ids = ids[landmark.point_ids]
        seen = sightings(scene.cloud.points[landmark.point_ids], of_epoch(scene.views, BEFORE))
        named = namer.name(outlined(seen[0], margin=0.6))["name"] if seen else "object"
        landmark.name = landmark.category if named == "object" else named
    return found


def _load_segmenter(log) -> Segmenter | None:
    try:
        return Segmenter()
    except (ImportError, OSError) as error:
        log(f"no segmenter ({error}); changes are described without nearby furniture")
        return None


def locate_regions(regions: list[Region], landmarks: list[Landmark]) -> None:
    """Replace the model's caption of where a region is with one measured against the furniture."""
    for region in regions:
        measured = place_phrase(region.box, landmarks)
        if measured:
            region.names["where"] = measured


def _load_embedder(log) -> Embedder | None:
    try:
        return Embedder()
    except ImportError as error:
        log(f"no appearance model ({error}); moves are matched on size and name only")
        return None


def run(before: Path, after: Path, out: Path, settings: Settings = Settings(), log=print) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    timer = Timer(log)
    views = reconstruct_videos(before, after, settings, log)
    timer.lap("reconstruction")
    views, cloud = to_room(views, settings)
    scene = judge(views, cloud, settings.tolerance)
    removed, added = regions_of(scene, settings.regions)
    log(f"{len(removed)} regions gone, {len(added)} regions new")
    timer.lap("change evidence")
    namer = make_namer(settings.namer)
    describe_regions(scene, removed + added, namer, _load_embedder(log))
    landmarks = name_landmarks(scene, namer, _load_segmenter(log), removed + added)
    locate_regions(removed + added, landmarks)
    log(f"furniture that stayed: {', '.join(lm.name for lm in landmarks) or 'none named'}")
    timer.lap("naming")
    moves = pair_moves(removed, added, scene.cloud.points, settings.matching)
    found = change_records.assemble(moves, removed, added, landmarks)
    for change in found:
        log(f"  {change.id} {change.type}: {change.sentence}")
    report = write_report(out, scene, found, landmarks, {"before": before, "after": after}, timer.spent)
    timer.lap("report")
    return report


def ceiling_height(scene: Scene) -> float:
    """Just under the ceiling, so its surface never joins the furniture below it."""
    return float(min(2.2, np.percentile(scene.cloud.points[:, 2], 99) - 0.3))


def counts_by_status(scene: Scene) -> dict:
    return {name: int(np.sum(scene.status == code)) for name, code in (("kept", KEPT), ("gone", GONE),
                                                                         ("unseen", UNSEEN))}
