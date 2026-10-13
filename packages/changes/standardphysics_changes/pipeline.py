"""From two videos to a list of changes, with the shared 3D scene they sit in."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import changes as change_records
from .evidence import UNSEEN, DepthLookup, Tolerance, classify, gather
from .export import unchecked_records, write_report
from .geometry import Cloud, apply, build_cloud, room_frame
from .landmarks import (
    Landmark,
    apart_from,
    find_landmarks,
    fitting_name,
    merge_touching,
    place_phrase,
    supports_under,
    vote_classes,
)
from .matching import MatchRules, pair_moves
from .naming import Embedder, Namer, Segmenter, make_namer
from .pictures import isolated, outlined, sightings
from .regions import Region, RegionRules, find_regions, finish_regions, one_sided_regions, settle
from .views import AFTER, BEFORE, View, load_views, of_epoch, save_views


@dataclass
class Settings:
    frames_per_video: int = 32
    voxel_m: float = 0.02
    namer: str = "auto"
    fov_deg: float | None = None
    camera_height_m: float | None = None
    rotate_cw: int = 0
    min_empty_share: float = 0.85
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
        with open(video, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    digest.update(f"{settings.frames_per_video}|{settings.fov_deg}|{settings.rotate_cw}".encode())
    return CACHE / f"{digest.hexdigest()[:16]}.npz"


def reconstruct_videos(before: Path, after: Path, settings: Settings, log) -> list[View]:
    cache = cache_path(before, after, settings)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if settings.reuse_reconstruction and cache.exists():
        log(f"reusing {cache}")
        return load_views(cache)
    from .reconstruct import reconstruct
    from .video import sample_frames

    first = sample_frames(before, settings.frames_per_video, settings.rotate_cw)
    second = sample_frames(after, settings.frames_per_video, settings.rotate_cw)
    log(f"sampled {len(first)} + {len(second)} frames")
    views = reconstruct(first, second, settings.fov_deg)
    save_views(views, cache)
    return views


def to_room(views: list[View], settings: Settings) -> tuple[list[View], Cloud, float]:
    """The views and cloud in the room frame, and the factor the reconstruction's scale was corrected by."""
    cloud = build_cloud(views, settings.voxel_m)
    transform = room_frame(views, cloud.points)
    cloud.points = apply(transform, cloud.points)
    views = [view.moved_by(transform) for view in views]
    factor = height_scale(views, settings.camera_height_m)
    if factor != 1.0:
        cloud.points = (cloud.points * factor).astype(np.float32)
        views = [view.scaled(factor) for view in views]
    return views, cloud, factor


def height_scale(views: list[View], camera_height_m: float | None) -> float:
    """How much to grow the room so the phone's median height above the floor is the one the person gave.

    The floor sits at z = 0 in the room frame, so a camera's z is its height. MapAnything's
    metric scale can be off by a tenth; how high someone held their phone is easy to know.
    """
    if camera_height_m is None:
        return 1.0
    measured = float(np.median([view.position[2] for view in views]))
    return camera_height_m / measured if measured > 0.2 else 1.0


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


def empty_share(scene: Scene, region: Region) -> float:
    """Of all the other video's sightlines that reached the region, the share that saw empty space there."""
    through = scene.through[region.point_ids].sum()
    looked = through + scene.agree[region.point_ids].sum()
    return float(through / looked) if looked else 0.0


def regions_of(scene: Scene, rules: RegionRules, min_empty_share: float) -> tuple[list[Region], list[Region]]:
    """Gone and new regions the other video agrees on.

    A region passes only when most sightlines into it saw empty space. On real footage the
    two reconstructions disagree by several centimetres, and an open-frame stool then reads
    as part empty from some angles; a real change reads as empty from nearly all of them.
    """
    found = {}
    for epoch, kind in ((BEFORE, "removed"), (AFTER, "added")):
        ids = np.flatnonzero(scene.cloud.epoch == epoch)
        regions = find_regions(scene.cloud.points[ids], scene.status[ids], kind, epoch, rules)
        for region in regions:
            region.point_ids = ids[region.point_ids]
        regions = finish_regions(regions, scene.cloud.points, rules)
        found[kind] = [region for region in regions if empty_share(scene, region) >= min_empty_share]
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
        names = namer.name(outlined(seen[0], margin=0.6)) if seen else {"name": "object", "detail": ""}
        landmark.name = fitting_name(landmark.category, names["name"])
        landmark.detail = names.get("detail", "")
    return found


def _load_segmenter(log) -> Segmenter | None:
    try:
        return Segmenter()
    except (ImportError, OSError) as error:
        log(f"no segmenter ({error}); changes are described without nearby furniture")
        return None


def locate_regions(regions: list[Region], landmarks: list[Landmark]) -> None:
    """Stand each region on what holds it up, then say where it is against the furniture.

    The measured phrase replaces the model's own caption of where the region is.
    """
    for region in regions:
        region.box = settle(region.box, [0.0, *supports_under(region.box, landmarks)])
        measured = place_phrase(region.box, landmarks)
        if measured:
            region.names["where"] = measured


NOT_OBJECTS = {"wall", "floor", "ceiling", "window", "door", "curtain", "shadow", "light", "corner", "object"}


def unchecked_regions(scene: Scene, changed: list[Region]) -> list[Region]:
    """Things only one video saw, in places the other never looked, apart from anything already reported."""
    found = []
    for epoch in (BEFORE, AFTER):
        ids = np.flatnonzero(scene.cloud.epoch == epoch)
        for region in one_sided_regions(scene.cloud.points[ids], scene.status[ids], epoch, ceiling_height(scene)):
            region.point_ids = ids[region.point_ids]
            near = any(np.linalg.norm(region.box.center[:2] - other.box.center[:2]) < 0.5 for other in changed)
            if not near:
                found.append(region)
    return found


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
    views, cloud, factor = to_room(views, settings)
    scene = judge(views, cloud, settings.tolerance)
    removed, added = regions_of(scene, settings.regions, settings.min_empty_share)
    log(f"{len(removed)} regions gone, {len(added)} regions new")
    timer.lap("change evidence")
    namer = make_namer(settings.namer)
    unchecked = unchecked_regions(scene, removed + added)
    describe_regions(scene, removed + added, namer, _load_embedder(log))
    describe_regions(scene, unchecked, namer, None)
    unchecked = [region for region in unchecked if region.names.get("name") not in NOT_OBJECTS]
    landmarks = name_landmarks(scene, namer, _load_segmenter(log), removed + added + unchecked)
    distinguish(landmarks, removed + added + unchecked)
    locate_regions(removed + added + unchecked, landmarks)
    log(f"seen by one video only: {', '.join(r.names.get('name', 'object') for r in unchecked) or 'nothing'}")
    log(f"furniture that stayed: {', '.join(lm.name for lm in landmarks) or 'none named'}")
    timer.lap("naming")
    moves = pair_moves(removed, added, scene.cloud.points, settings.matching)
    found = change_records.assemble(moves, removed, added, landmarks)
    for change in found:
        log(f"  {change.id} {change.type}: {change.sentence}")
    scale = {"factor": round(factor, 4), "from": "camera height" if settings.camera_height_m else "reconstruction"}
    report = write_report(out, scene, found, landmarks, {"before": before, "after": after},
                          {"seconds": timer.spent, "scale": scale, "unchecked": unchecked_records(scene, unchecked, out)})
    timer.lap("report")
    return report


def distinguish(landmarks: list[Landmark], regions: list[Region]) -> None:
    """Give every piece of furniture a name nothing else in the room shares.

    A piece named like a change, or like another piece, takes the model's short description
    instead ("white ceramic pot"). When that is long or still shared, the piece keeps its
    label in the viewer but no sentence points to it, since "beside the chair" would not
    say which chair.
    """
    taken = [region.names.get("name") for region in regions] + [landmark.name for landmark in landmarks]
    for landmark in landmarks:
        if taken.count(landmark.name) == 1:
            continue
        detail = landmark.detail
        fits = bool(detail) and fitting_name(landmark.category, detail) == detail
        if fits and len(detail.split()) <= 4 and taken.count(detail) == 0:
            taken.append(detail)
            landmark.name = detail
        else:
            landmark.ambiguous = True


def ceiling_height(scene: Scene) -> float:
    """Just under the ceiling, so its surface never joins the furniture below it."""
    return float(min(2.2, np.percentile(scene.cloud.points[:, 2], 99) - 0.3))
