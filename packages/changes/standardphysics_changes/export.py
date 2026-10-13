"""Write scene.json, the shared point cloud and before-and-after pictures of every change."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from . import language
from .changes import Change, confidence
from .evidence import GONE, KEPT, UNSEEN, DepthLookup, Tolerance, compare
from .landmarks import inside_box
from .pictures import box_pixels, detail_crop, empty_spot_view, padded_bounds, sightings
from .regions import Box, Region
from .views import AFTER, BEFORE, EPOCH_NAMES, View, of_epoch

FORMAT_VERSION = 1
# The scorer and the command line can change without changing what is detected.
NOT_DETECTOR = {"evaluate.py", "cli.py", "__main__.py"}


def detector_fingerprint() -> str:
    """A hash of the detector's own source, so a result says exactly which detector made it."""
    digest = hashlib.sha1()
    for source in sorted(Path(__file__).parent.glob("*.py")):
        if source.name not in NOT_DETECTOR:
            digest.update(source.name.encode())
            digest.update(source.read_bytes())
    return digest.hexdigest()[:12]


def _round(values, digits: int = 3) -> list:
    return [round(float(v), digits) for v in np.asarray(values).ravel()]


def box_record(box: Box) -> dict:
    return {**box.as_dict(), "corners": [_round(c) for c in box.corners()]}


def picture(view: View, box: Box, path: Path, margin: float = 0.6) -> dict | None:
    """Crop the view around the box and keep the box's corners in the crop's 0-1 coordinates."""
    pixels = box_pixels(box, view)
    if pixels is None:
        return None
    height, width = view.shape
    low, high = pixels.min(axis=0), pixels.max(axis=0)
    if high[0] < 0 or high[1] < 0 or low[0] > width or low[1] > height:
        return None
    bounds = padded_bounds(max(low[0], 0), max(low[1], 0), min(high[0], width), min(high[1], height),
                           view.shape, margin)
    left, top, right, bottom = bounds
    detail_crop(view, bounds).save(path, quality=88)
    corners = (pixels - [left, top]) / [right - left, bottom - top]
    return {
        "file": f"pictures/{path.name}",
        "video": EPOCH_NAMES[view.epoch],
        "time_s": round(view.time_s, 2),
        "aspect": round((right - left) / (bottom - top), 3),
        "box": [_round(c) for c in corners],
    }


def _sighting_view(region: Region, scene) -> View | None:
    seen = sightings(scene.cloud.points[region.point_ids], of_epoch(scene.views, region.epoch))
    return seen[0].view if seen else None


def _pictures(change: Change, scene, folder: Path) -> dict:
    """The object where it was and where it is; an empty spot stands in for whichever side it is missing."""
    shots = {}
    for side, epoch, region in (("before", BEFORE, change.before), ("after", AFTER, change.after)):
        subject = region or change.subject
        if region is not None:
            view = _sighting_view(region, scene)
        else:
            view = empty_spot_view(scene.cloud.points[subject.point_ids], of_epoch(scene.views, epoch))
        if view is not None:
            shots[side] = picture(view, subject.box, folder / f"{change.id}-{side}.jpg")
    return {side: shot for side, shot in shots.items() if shot}


def frames_seeing_empty(region: Region, scene, tolerance: Tolerance = Tolerance()) -> dict:
    """How many of the other video's frames looked at this spot and saw mostly empty space there."""
    points = scene.cloud.points[region.point_ids]
    others = of_epoch(scene.views, 1 - region.epoch)
    empty = 0
    for view in others:
        agree, through, _ = compare(points, DepthLookup.of(view, tolerance), tolerance)
        if through.sum() >= 15 and through.sum() >= agree.sum():
            empty += 1
    return {"empty_in": empty, "of": len(others), "video": EPOCH_NAMES[1 - region.epoch]}


def change_record(change: Change, scene, folder: Path) -> dict:
    subject = change.subject
    ids = subject.point_ids
    record = {
        "id": change.id,
        "type": change.type,
        "name": change.name,
        "detail": change.detail,
        "sentence": change.sentence,
        "partly_seen": change.partly_seen,
        "size": _round(subject.box.size, 2),
        "size_text": language.size_phrase(subject.box.size),
        "confidence": confidence(subject, scene.through[ids], scene.agree[ids]),
        "evidence": {
            "points": int(len(ids)),
            "old_spot": frames_seeing_empty(change.before, scene) if change.before else None,
            "new_spot": frames_seeing_empty(change.after, scene) if change.after else None,
        },
        "before": _place(change.before, change.where_before),
        "after": _place(change.after, change.where_after),
        "pictures": _pictures(change, scene, folder),
    }
    if change.type == "moved":
        turn = None if change.turn_deg is None else round(change.turn_deg)
        record |= {"distance_m": round(change.distance_m, 2), "turn_deg": turn,
                   "similarity": round(float(change.similarity or 0), 2)}
    return record


def _place(region: Region | None, where: str) -> dict | None:
    if region is None:
        return None
    return {"box": box_record(region.box), "where": where}


def camera_record(view: View) -> dict:
    height, width = view.shape
    return {
        "video": EPOCH_NAMES[view.epoch],
        "frame": view.frame_index,
        "time_s": round(view.time_s, 2),
        "position": _round(view.position),
        "rotation": _round(view.cam_to_world[:3, :3], 4),
        "fov_y_deg": round(float(np.degrees(2 * np.arctan(height / 2 / view.intrinsics[1, 1]))), 2),
        "aspect": round(width / height, 4),
    }


def write_cloud(path: Path, scene, found: list[Change]) -> dict:
    cloud = scene.cloud
    change_of = np.zeros(len(cloud), dtype=np.uint8)
    for number, change in enumerate(found, start=1):
        for region in change.regions:
            inside = inside_box(cloud.points[region.point_ids], region.box, margin_m=0.05)
            change_of[region.point_ids[inside]] = number
    display = np.where(scene.status == GONE, KEPT, scene.status).astype(np.uint8)
    parts = [cloud.points.astype("<f4"), cloud.colors.astype(np.uint8), cloud.epoch.astype(np.uint8), display,
             change_of]
    with open(path, "wb") as handle:
        for part in parts:
            handle.write(np.ascontiguousarray(part).tobytes())
    return {
        "file": path.name,
        "count": int(len(cloud)),
        "layout": ["position float32 x3", "color uint8 x3", "video uint8", "seen uint8", "change uint8"],
        "seen_codes": {"0": "seen again by the other video", str(UNSEEN): "never seen by the other video"},
    }


def coverage(scene) -> dict:
    shares = {}
    for epoch in (BEFORE, AFTER):
        mine = scene.cloud.epoch == epoch
        checked = np.isin(scene.status[mine], [KEPT, GONE]).mean() if mine.any() else 0.0
        shares[f"{EPOCH_NAMES[epoch]}_checked_by_other"] = round(float(checked), 3)
    return shares


def playable_copy(source: Path, target: Path) -> str | None:
    """A small H.264 copy of an input video for the viewer; phones often record HEVC, which not every browser plays."""
    if target.resolve() == source.resolve():
        return target.name
    if shutil.which("ffmpeg") is None:
        return None
    command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vf", "scale=-2:'min(540,ih)'",
               "-c:v", "libx264", "-crf", "26", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an",
               "-movflags", "+faststart", str(target)]
    return target.name if subprocess.run(command, check=False).returncode == 0 else None


def _unchecked_sentence(region: Region, detail: str, where: str) -> str:
    if region.doubt == "unsupported":
        return language.unsupported_sentence(detail, region.kind, float(region.box.center[2] - region.box.size[2] / 2))
    return language.unchecked_sentence(detail, where, EPOCH_NAMES[region.epoch])


def unchecked_records(scene, regions: list[Region], out: Path) -> list[dict]:
    """Things only one video saw, or that hang in the air. They are listed, never counted as changes."""
    folder = out / "pictures"
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    for number, region in enumerate(regions, start=1):
        identifier, video = f"u{number}", EPOCH_NAMES[region.epoch]
        name, detail, where = (region.names.get(key, "") for key in ("name", "detail", "where"))
        view = _sighting_view(region, scene)
        shot = picture(view, region.box, folder / f"{identifier}.jpg") if view is not None else None
        records.append({
            "id": identifier, "video": video, "name": name or "object", "detail": detail or "object",
            "reason": region.doubt or "one video", "sentence": _unchecked_sentence(region, detail or name or "object", where),
            "box": box_record(region.box), "size_text": language.size_phrase(region.box.size), "picture": shot,
        })
    return records


def landmark_record(landmark) -> dict:
    return {"name": landmark.name, "box": box_record(landmark.box)}


def write_report(out: Path, scene, found: list[Change], landmarks: list, inputs: dict, extras: dict) -> dict:
    folder = out / "pictures"
    folder.mkdir(exist_ok=True)
    records = [change_record(change, scene, folder) for change in found]
    low, high = np.percentile(scene.cloud.points, [1, 99], axis=0)
    report = {
        "format": FORMAT_VERSION,
        "detector": detector_fingerprint(),
        "inputs": {side: Path(path).name for side, path in inputs.items()},
        "videos": {side: playable_copy(Path(path), out / f"{side}.mp4") for side, path in inputs.items()},
        "summary": language.summary(records),
        "changes": records,
        "furniture": [landmark_record(landmark) for landmark in landmarks if landmark.name],
        "coverage": coverage(scene),
        "room": {"low": _round(low), "high": _round(high)},
        "cloud": write_cloud(out / "cloud.bin", scene, found),
        "cameras": [camera_record(view) for view in scene.views],
        **extras,
    }
    (out / "scene.json").write_text(json.dumps(report, indent=1))
    return report
