"""From two videos to a list of changes, with the shared 3D scene they sit in."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import numpy as np

from . import changes as change_records
from . import language
from .evidence import UNSEEN, DepthLookup, Tolerance, classify, gather
from .export import unchecked_records, write_report
from .geometry import Cloud, apply, build_cloud, room_frame
from .landmarks import (
    Landmark,
    apart_from,
    find_landmarks,
    fits_kind,
    fitting_name,
    footprint_gap,
    merge_touching,
    place_phrase,
    settle_kind,
    supports_under,
    touches_furniture,
    vote_classes,
)
from .matching import MatchRules, absorb_fragments, match_heights, pair_moves
from .naming import Embedder, Namer, PlainNamer, Segmenter, agreed_names, make_namer
from .pictures import isolated, outlined, runs_off_frame, sightings
from .regions import (
    Region,
    RegionRules,
    find_regions,
    finish_regions,
    fit_box,
    one_sided_regions,
    settle,
    support_share,
)
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
        views = [outlined(sighting, margin=1.2) for sighting in clearest_two(seen)]
        plain = language.plain_noun(region.box.size)
        region.names = agreed_names(namer, views) or {"name": plain, "detail": plain, "where": ""}
        region.cut_off = never_seen_whole(seen)
        if embedder is not None:
            region.descriptor = embedder.embed([isolated(s) for s in seen[:3]])


def split_oversized(scene: Scene, regions: list[Region], rules: RegionRules, namer: Namer,
                    embedder: Embedder | None) -> list[Region]:
    """Re-cut a region too big for what it is named, such as a chair grown into the bin beside it.

    Two objects a few centimetres apart join through the unseen floor between them. Their
    seed points part on a grid half as fine; the pieces are kept, and named on their own,
    only when at least two of them are big enough to be objects.
    """
    out = []
    for region in regions:
        pieces = [] if fits_kind(region.box, region.names.get("name", "")) else _finer_pieces(scene, region, rules)
        if len(pieces) < 2:
            out.append(region)
            continue
        describe_regions(scene, pieces, namer, embedder)
        out.extend(pieces)
    return out


def _finer_pieces(scene: Scene, region: Region, rules: RegionRules) -> list[Region]:
    ids = region.point_ids
    finer = replace(rules, voxel_m=rules.voxel_m / 2)
    pieces = finish_regions(find_regions(scene.cloud.points[ids], scene.status[ids], region.kind, region.epoch, finer),
                            scene.cloud.points[ids], finer)
    for piece in pieces:
        piece.point_ids = ids[piece.point_ids]
    return _rejoin_small(pieces, scene.cloud.points)


def _rejoin_small(pieces: list[Region], points: np.ndarray, share: float = 0.25, reach_m: float = 0.1) -> list[Region]:
    """Pieces much smaller than the biggest go back to a bigger piece they touch, like a bin's leaning lid."""
    if len(pieces) < 2:
        return pieces
    biggest = max(len(piece.point_ids) for piece in pieces)
    large = [piece for piece in pieces if len(piece.point_ids) >= share * biggest]
    for piece in (piece for piece in pieces if len(piece.point_ids) < share * biggest):
        host = min(large, key=lambda other: footprint_gap(other.box, piece.box))
        if footprint_gap(host.box, piece.box) > reach_m:
            large.append(piece)
            continue
        host.point_ids = np.union1d(host.point_ids, piece.point_ids)
        host.box = fit_box(points[host.point_ids])
    return large


def clearest_two(seen: list) -> list:
    """The best view, and the next one when it shows at least half as much, so the namer can cross-check."""
    return seen[:1] + [sighting for sighting in seen[1:2] if sighting.visible >= 0.5 * seen[0].visible]


def unsupported(regions: list[Region], points: np.ndarray, changed_ids: np.ndarray,
                min_share: float = 0.75) -> tuple[list[Region], list[Region]]:
    """Split off raised regions with nothing under most of their footprint; things rest on something.

    A box hanging in the air is more likely a misread surface than a new object, so it is
    listed as not counted, with the reason, instead of being reported.
    """
    still = np.delete(points, changed_ids, axis=0)
    kept, doubted = [], []
    for region in regions:
        if support_share(region.box, still) >= min_share:
            kept.append(region)
            continue
        region.doubt = "unsupported"
        doubted.append(region)
    return kept, doubted


def never_seen_whole(seen: list) -> bool:
    """No good view shows the region ending inside the frame: in every one its surface runs off the edge.

    A vase near the top of the frame runs off in most views, but two show its top, so its
    full height was seen; a crate beside the camera's path runs off in every view there is.
    """
    best = max(sighting.visible for sighting in seen)
    return all(runs_off_frame(sighting) for sighting in seen if sighting.visible >= 0.5 * best)


def name_landmarks(scene: Scene, namer: Namer, segmenter: Segmenter | None, gone: list[Region]) -> list[Landmark]:
    """Find and name the unchanged furniture of the before video, which the change sentences point to.

    `gone` holds the regions that disappeared, removed things and the old spots of moved
    ones. Only something that left can leave scraps behind; a basket set on a nightstand
    does not make the nightstand a scrap.
    """
    if segmenter is None:
        return []
    ids = np.flatnonzero(scene.cloud.epoch == BEFORE)
    points = scene.cloud.points[ids]
    views = of_epoch(scene.views, BEFORE)[::2]
    classes = vote_classes(points, views, [segmenter.classes(view.image) for view in views])
    found = find_landmarks(points, scene.status[ids], classes, segmenter.names, ceiling_height(scene))
    left = [(region.box, region.names.get("name", "")) for region in gone]
    found = merge_touching(apart_from(found, points, left), points)
    named = []
    for landmark in found:
        landmark.point_ids = ids[landmark.point_ids]
        seen = sightings(scene.cloud.points[landmark.point_ids], of_epoch(scene.views, BEFORE))
        views = [outlined(sighting, margin=0.6) for sighting in clearest_two(seen)]
        names = (agreed_names(namer, views) if seen else None) or {"name": "object", "detail": ""}
        if settle_kind(landmark, names["name"]):
            landmark.name = fitting_name(landmark.category, names["name"])
            landmark.detail = names.get("detail", "")
            named.append(landmark)
    return named


def _load_segmenter(log) -> Segmenter | None:
    try:
        return Segmenter()
    except (ImportError, OSError) as error:
        log(f"no segmenter ({error}); changes are described without nearby furniture")
        return None


def locate_regions(regions: list[Region], landmarks: list[Landmark], points: np.ndarray) -> None:
    """Stand each region on what holds it up, then say where it is against the furniture.

    Only a measured phrase is kept. The vision model also guesses a location, but a guess
    the geometry never checked could put an object beside furniture metres away, so with
    nothing measured the sentence says no location at all.
    """
    for region in regions:
        region.box = settle(region.box, [0.0, *supports_under(region.box, landmarks, points)])
        region.names["where"] = place_phrase(region.box, landmarks, subject=region.names.get("name", ""))


# Words that make a name part of the building, or a passer-by, rather than a thing in the room.
STRUCTURE = {"wall", "floor", "ceiling", "window", "door", "curtain", "shadow", "corner", "section", "counter",
             "pillar", "column", "beam", "pipe", "rail", "railing", "stairs", "staircase", "reflection", "glass",
             "person", "people", "man", "woman", "child"}


def objects_only(regions: list[Region], named_by_model: bool) -> list[Region]:
    """Drop clumps a vision model called part of the room. With no model, every clump stays.

    Only the last word decides, the noun the rest describes: a "glass vase" and a "counter
    stool" are things, a "glass wall" and a "bar counter" are the building.
    """
    if not named_by_model:
        return regions
    return [region for region in regions if region.names.get("name", "object").split()[-1:] != []
            and region.names.get("name", "object").split()[-1] not in STRUCTURE]


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
        log(f"no appearance model ({error}); a move is paired only when both ends get the same specific name")
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
    embedder = _load_embedder(log)
    describe_regions(scene, removed + added, namer, embedder)
    removed = split_oversized(scene, removed, settings.regions, namer, embedder)
    added = split_oversized(scene, added, settings.regions, namer, embedder)
    describe_regions(scene, unchecked, namer, None)
    landmarks = name_landmarks(scene, namer, _load_segmenter(log), removed)
    unchecked = [region for region in objects_only(unchecked, not isinstance(namer, PlainNamer))
                 if not touches_furniture(region.box, landmarks) and fits_kind(region.box, region.names.get("name", ""))]
    distinguish(landmarks, removed + added + unchecked)
    locate_regions(removed + added + unchecked, landmarks, scene.cloud.points)
    log(f"seen by one video only: {', '.join(r.names.get('name', 'object') for r in unchecked) or 'nothing'}")
    for region in unchecked:
        region.doubt = region.doubt or "one video"
    log(f"furniture that stayed: {', '.join(lm.name for lm in landmarks) or 'none named'}")
    timer.lap("naming")
    moves = pair_moves(removed, added, scene.cloud.points, settings.matching)
    paired = {id(move.removed) for move in moves} | {id(move.added) for move in moves}
    loose_removed, loose_added = absorb_fragments(moves, [r for r in removed if id(r) not in paired],
                                                  [r for r in added if id(r) not in paired], scene.cloud.points)
    match_heights(moves)
    changed_ids = np.unique(np.concatenate([region.point_ids for region in removed + added] or [np.array([], int)]))
    loose_removed, doubted_removed = unsupported(loose_removed, scene.cloud.points, changed_ids)
    loose_added, doubted_added = unsupported(loose_added, scene.cloud.points, changed_ids)
    unchecked += doubted_removed + doubted_added
    found = change_records.assemble(moves, loose_removed, loose_added, landmarks)
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
    taken = [region.names.get("name", "") for region in regions] + [landmark.name for landmark in landmarks]
    for landmark in landmarks:
        if not _collides(landmark.name, taken):
            continue
        detail = landmark.detail
        fits = bool(detail) and fitting_name(landmark.category, detail) == detail
        if fits and len(detail.split()) <= 4 and not _collides(detail, taken + [detail]):
            taken.append(detail)
            landmark.name = detail
        else:
            landmark.ambiguous = True


def _collides(name: str, taken: list[str]) -> bool:
    """Used twice, or inside a longer name, so "the chair" next to "the wooden chair" says no one chair."""
    words = set(name.split())
    others = list(taken)
    if name in others:
        others.remove(name)
    return any(words <= set(other.split()) for other in others if other)


def ceiling_height(scene: Scene) -> float:
    """Just under the ceiling, so its surface never joins the furniture below it."""
    return float(min(2.2, np.percentile(scene.cloud.points[:, 2], 99) - 0.3))
