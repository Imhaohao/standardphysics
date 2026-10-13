"""Score a result against a rendered room's ground truth.

The estimated camera path is lined up with the true one twice. A rigid fit (turn and
shift only) keeps the reconstruction's own metres, so its errors are the ones a person
reading the sentences would meet. A similarity fit also takes out the scale, which shows
how good the shape is on its own and decides which reported change belongs to which true one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAME_THING = {
    "armchair": {"armchair", "chair", "accent chair", "lounge chair"},
    "potted plant": {"potted plant", "plant", "houseplant"},
    "cardboard box": {"cardboard box", "box", "carton"},
    "wicker basket": {"basket", "wicker basket", "woven basket", "bamboo basket"},
    "wooden stool": {"stool", "wooden stool", "bar stool"},
    "ottoman": {"ottoman", "footstool", "pouf"},
    "wooden crate": {"crate", "wooden crate", "wooden box"},
    "plastic crate": {"crate", "plastic crate", "plastic box", "storage bin", "storage crate"},
    "brass vase": {"vase", "brass vase"},
}
CLOSE_M = 0.5


@dataclass
class Fit:
    scale: float
    rotation: np.ndarray
    shift: np.ndarray

    def point(self, point) -> np.ndarray:
        return self.scale * self.rotation @ np.asarray(point, dtype=float) + self.shift

    @property
    def yaw_deg(self) -> float:
        return float(np.degrees(np.arctan2(self.rotation[1, 0], self.rotation[0, 0])))


def umeyama(source: np.ndarray, target: np.ndarray, with_scale: bool = True) -> tuple[float, np.ndarray, np.ndarray]:
    """Scale, rotation and translation taking `source` points onto `target` points."""
    mu_s, mu_t = source.mean(axis=0), target.mean(axis=0)
    s, t = source - mu_s, target - mu_t
    u, d, vt = np.linalg.svd(t.T @ s / len(source))
    flip = np.eye(3)
    flip[2, 2] = np.sign(np.linalg.det(u @ vt))
    rotation = u @ flip @ vt
    scale = float(np.trace(np.diag(d) @ flip) / s.var(axis=0).sum()) if with_scale else 1.0
    return scale, rotation, mu_t - scale * rotation @ mu_s


def name_matches(truth_label: str, predicted: str) -> bool:
    return predicted.lower().strip() in SAME_THING.get(truth_label, {truth_label})


def _wrap(degrees: float) -> float:
    return (degrees + 180) % 360 - 180


def _footprint(centre, size, yaw_deg, grid: np.ndarray) -> np.ndarray:
    c, s = np.cos(np.radians(-yaw_deg)), np.sin(np.radians(-yaw_deg))
    offset = grid - np.asarray(centre)[:2]
    local = offset @ np.array([[c, s], [-s, c]])
    return np.all(np.abs(local) <= np.asarray(size)[:2] / 2, axis=1)


def box_overlap(a: dict, b: dict, step_m: float = 0.01) -> float:
    """Intersection over union of two upright boxes, each a centre, a size and a yaw."""
    reach = max(np.linalg.norm(a["size"][:2]), np.linalg.norm(b["size"][:2]))
    low = np.minimum(a["center"][:2], b["center"][:2]) - reach
    high = np.maximum(a["center"][:2], b["center"][:2]) + reach
    xs, ys = np.arange(low[0], high[0], step_m), np.arange(low[1], high[1], step_m)
    grid = np.stack(np.meshgrid(xs, ys), axis=-1).reshape(-1, 2)
    shared_floor = np.sum(_footprint(a["center"], a["size"], a["yaw_deg"], grid)
                          & _footprint(b["center"], b["size"], b["yaw_deg"], grid)) * step_m ** 2
    bottoms = [box["center"][2] - box["size"][2] / 2 for box in (a, b)]
    tops = [box["center"][2] + box["size"][2] / 2 for box in (a, b)]
    shared = shared_floor * max(0.0, min(tops) - max(bottoms))
    volumes = [float(np.prod(box["size"])) for box in (a, b)]
    return float(shared / (volumes[0] + volumes[1] - shared)) if shared > 0 else 0.0


def in_truth_frame(box: dict, fit: Fit) -> dict:
    return {"center": fit.point(box["center"]), "size": np.asarray(box["size"]) * fit.scale,
            "yaw_deg": box["yaw_deg"] + fit.yaw_deg}


def _floor_distance(a, b) -> float:
    if a is None and b is None:
        return 0.0
    if a is None or b is None:
        return np.inf
    return float(np.linalg.norm(np.asarray(a)[:2] - np.asarray(b)[:2]))


def _centre(place: dict | None, fit: Fit):
    return None if place is None else fit.point(place["box"]["center"])


def _truth_centre(box: dict | None):
    return None if box is None else np.asarray(box["center"])


def match_error(truth: dict, change: dict, fit: Fit) -> float:
    return max(_floor_distance(_truth_centre(truth[side]), _centre(change[side], fit)) for side in ("before", "after"))


def _side_errors(truth_box: dict | None, place: dict | None, fit: Fit) -> dict:
    if truth_box is None or place is None:
        return {}
    measured = in_truth_frame(place["box"], fit)
    bottom = measured["center"][2] - measured["size"][2] / 2
    true_bottom = truth_box["center"][2] - truth_box["size"][2] / 2
    return {
        "centre_error_m": round(_floor_distance(measured["center"], truth_box["center"]), 3),
        "bottom_error_m": round(float(bottom - true_bottom), 3),
        "height_error_m": round(float(measured["size"][2] - truth_box["size"][2]), 3),
        "overlap": round(box_overlap(measured, {**truth_box, "center": np.asarray(truth_box["center"])}), 2),
    }


def _move_errors(item: dict, change: dict) -> dict:
    true_distance = _floor_distance(item["before"]["center"], item["after"]["center"])
    true_turn = _wrap(item["after"]["yaw_deg"] - item["before"]["yaw_deg"])
    row = {"true_distance_m": round(true_distance, 3), "reported_distance_m": change["distance_m"],
           "distance_error_m": round(abs(change["distance_m"] - true_distance), 3), "true_turn_deg": round(true_turn)}
    if change.get("turn_deg") is not None:
        row["turn_error_deg"] = round(abs(_wrap(change["turn_deg"] - true_turn)))
    return row


MIN_OVERLAP = 0.25


def _best_overlap(row: dict) -> float:
    return max((row[side]["overlap"] for side in ("before", "after") if side in row), default=0.0)


def _score_one(item: dict, predictions: list[dict], fits: dict[str, Fit], used: set) -> dict:
    """A true change is found when a report of its type sits within 50 cm and its box covers a real part of it.

    A report nearby whose box overlaps the object by less than a quarter is recorded as partial:
    it points at the right spot but did not find the object's extent.
    """
    candidates = [(c, match_error(item, c, fits["shape"])) for c in predictions
                  if c["type"] == item["type"] and c["id"] not in used]
    change, error = min(candidates, key=lambda pair: pair[1], default=(None, np.inf))
    if change is None or error > CLOSE_M:
        return {"truth": item["label"], "type": item["type"], "found": None}
    used.add(change["id"])
    row = {"truth": item["label"], "type": item["type"], "found": change["id"], "name": change["name"],
           "name_ok": name_matches(item["label"], change["name"]), "shape_position_error_m": round(error, 3)}
    for side in ("before", "after"):
        errors = _side_errors(item[side], change[side], fits["metres"])
        if errors:
            row[side] = errors
    if item["type"] == "moved":
        row |= _move_errors(item, change)
    if _best_overlap(row) < MIN_OVERLAP:
        row["partial"], row["found"] = row["found"], None
    return row


def camera_fits(scene: dict, truth: dict) -> tuple[dict[str, Fit], float]:
    estimated = np.array([camera["position"] for camera in scene["cameras"]])
    actual = np.array([np.array(truth["cameras_opencv_c2w"][camera["video"]][camera["frame"]])[:3, 3]
                       for camera in scene["cameras"]])
    shape = Fit(*umeyama(estimated, actual))
    metres = Fit(*umeyama(estimated, actual, with_scale=False))
    residual = actual - np.array([shape.point(point) for point in estimated])
    return {"shape": shape, "metres": metres}, float(np.sqrt((residual ** 2).sum(axis=1).mean()))


def _reported_unverifiable(truth: dict, predictions: list[dict], fit: Fit) -> list[str]:
    hits = []
    for item in truth.get("unverifiable", []):
        spot = _truth_centre(item["after"] or item["before"])
        for change in predictions:
            places = [change[side] for side in ("before", "after") if change[side]]
            if any(_floor_distance(spot, fit.point(place["box"]["center"])) <= CLOSE_M for place in places):
                hits.append(f"{change['id']} reported {item['label']}, which the before video never saw")
    return hits


def _listed_unverifiable(truth: dict, scene: dict, fit: Fit) -> list[str]:
    """True changes the before video never saw that the result lists as seen by one video only."""
    listed = []
    for item in truth.get("unverifiable", []):
        spot = _truth_centre(item["after"] or item["before"])
        for thing in scene.get("unchecked", []):
            if _floor_distance(spot, fit.point(thing["box"]["center"])) <= CLOSE_M:
                listed.append(f"{thing['id']} lists the {item['label']} as seen once")
    return listed


def phantom_furniture(scene: dict, truth: dict, fit: Fit) -> list[str]:
    """Furniture the result names that stands on no real object, so a sentence citing it would invent a landmark."""
    boxes = [box for item in truth.get("objects", {}).values() for box in (item["before"], item["after"]) if box]
    phantoms = []
    for piece in scene.get("furniture", []):
        centre = fit.point(piece["box"]["center"])
        reaches = [max(0.5, 0.5 * float(np.hypot(*box["size"][:2]))) for box in boxes]
        if not any(_floor_distance(centre, box["center"]) <= reach for box, reach in zip(boxes, reaches)):
            phantoms.append(piece["name"])
    return phantoms


def _mean(values: list[float]) -> float | None:
    return round(float(np.mean(values)), 3) if values else None


def _totals(rows: list[dict], scene: dict, fits: dict[str, Fit], rmse: float, unverifiable: list[str],
            listed: list[str]) -> dict:
    found = [row for row in rows if row["found"]]
    partial = [row for row in rows if row.get("partial")]
    sides = [row[side] for row in found for side in ("before", "after") if side in row]
    moves = [row for row in found if row["type"] == "moved"]
    matched = {row["found"] for row in found} | {row["partial"] for row in partial}
    return {
        "camera_alignment": {"scale": round(fits["shape"].scale, 3), "rmse_m": round(rmse, 3)},
        "recall": round(len(found) / len(rows), 3) if rows else None,
        "precision": round(len(found) / len(scene["changes"]), 3) if scene["changes"] else None,
        "partial": [f"{row['partial']} points at the {row['truth']} but covers too little of it" for row in partial],
        "names_correct": f"{sum(row['name_ok'] for row in found)} of {len(found)}",
        "mean_centre_error_m": _mean([side["centre_error_m"] for side in sides]),
        "mean_bottom_error_m": _mean([abs(side["bottom_error_m"]) for side in sides]),
        "mean_height_error_m": _mean([abs(side["height_error_m"]) for side in sides]),
        "mean_overlap": _mean([side["overlap"] for side in sides]),
        "mean_distance_error_m": _mean([row["distance_error_m"] for row in moves]),
        "false_alarms": [c["id"] for c in scene["changes"] if c["id"] not in matched],
        "unverifiable_reported": unverifiable,
        "unverifiable_listed": listed,
        "changes": rows,
    }


def score(scene: dict, truth: dict) -> dict:
    fits, rmse = camera_fits(scene, truth)
    used: set = set()
    rows = [_score_one(item, scene["changes"], fits, used) for item in truth["changes"]]
    reported = _reported_unverifiable(truth, scene["changes"], fits["shape"])
    totals = _totals(rows, scene, fits, rmse, reported, _listed_unverifiable(truth, scene, fits["shape"]))
    return {**totals, "phantom_furniture": phantom_furniture(scene, truth, fits["shape"])}


def evaluate(result_dir: Path, truth_path: Path) -> dict:
    scene = json.loads((result_dir / "scene.json").read_text())
    report = score(scene, json.loads(truth_path.read_text()))
    (result_dir / "evaluation.json").write_text(json.dumps(report, indent=1))
    return report
