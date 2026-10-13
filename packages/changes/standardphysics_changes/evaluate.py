"""Score a result against the rendered room's ground truth.

The estimated cameras are lined up with the true ones by a similarity transform, so
the score also says whether the reconstruction's metres are real metres.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SAME_THING = {
    "armchair": {"chair", "armchair", "accent chair", "lounge chair"},
    "potted plant": {"plant", "potted plant", "houseplant", "tree", "pot"},
    "cardboard box": {"box", "cardboard box", "carton", "package"},
    "wicker basket": {"basket", "wicker basket", "hamper"},
    "wooden stool": {"stool", "wooden stool", "seat", "chair"},
}
CLOSE_M = 0.5


def umeyama(source: np.ndarray, target: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Scale, rotation and translation taking `source` points onto `target` points."""
    mu_s, mu_t = source.mean(axis=0), target.mean(axis=0)
    s, t = source - mu_s, target - mu_t
    u, d, vt = np.linalg.svd(t.T @ s / len(source))
    flip = np.eye(3)
    flip[2, 2] = np.sign(np.linalg.det(u @ vt))
    rotation = u @ flip @ vt
    scale = float(np.trace(np.diag(d) @ flip) / s.var(axis=0).sum())
    return scale, rotation, mu_t - scale * rotation @ mu_s


def name_matches(truth_label: str, predicted: str) -> bool:
    predicted = predicted.lower()
    words = SAME_THING.get(truth_label, {truth_label})
    return any(word in predicted or predicted in word for word in words)


def _centre(place: dict | None, align) -> np.ndarray | None:
    if place is None:
        return None
    return align(np.array(place["box"]["center"]))


def _truth_centre(box: dict | None) -> np.ndarray | None:
    return None if box is None else np.array(box["center"])


def _distance(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None and b is None:
        return 0.0
    if a is None or b is None:
        return np.inf
    return float(np.linalg.norm(a[:2] - b[:2]))


def _match_error(truth: dict, change: dict, align) -> float:
    errors = [
        _distance(_truth_centre(truth["before"]), _centre(change["before"], align)),
        _distance(_truth_centre(truth["after"]), _centre(change["after"], align)),
    ]
    return max(errors)


def score(scene: dict, truth: dict) -> dict:
    estimated, actual = [], []
    for camera in scene["cameras"]:
        estimated.append(camera["position"])
        actual.append(np.array(truth["cameras_opencv_c2w"][camera["video"]][camera["frame"]])[:3, 3])
    scale, rotation, shift = umeyama(np.array(estimated), np.array(actual))
    residual = np.array(actual) - (scale * np.array(estimated) @ rotation.T + shift)

    def align(point: np.ndarray) -> np.ndarray:
        return scale * rotation @ point + shift

    rows, used = [], set()
    for item in truth["changes"]:
        rows.append(_score_one(item, scene["changes"], align, used))
    return _totals(rows, scene, scale, residual)


def _score_one(item: dict, predictions: list[dict], align, used: set) -> dict:
    candidates = [(c, _match_error(item, c, align)) for c in predictions if c["type"] == item["type"]
                  and c["id"] not in used]
    hit = min(candidates, key=lambda pair: pair[1], default=(None, np.inf))
    if hit[0] is None or hit[1] > CLOSE_M:
        return {"truth": item["label"], "type": item["type"], "found": None}
    change = hit[0]
    used.add(change["id"])
    row = {"truth": item["label"], "type": item["type"], "found": change["id"], "name": change["name"],
           "name_ok": name_matches(item["label"], change["name"]), "position_error_m": round(hit[1], 3)}
    if item["type"] == "moved":
        true_distance = _distance(_truth_centre(item["before"]), _truth_centre(item["after"]))
        measured = _distance(_centre(change["before"], align), _centre(change["after"], align))
        row["distance_error_m"] = round(abs(measured - true_distance), 3)
        row |= _turn_error(item, change)
    return row


def _wrap(degrees: float) -> float:
    return (degrees + 180) % 360 - 180


def _turn_error(item: dict, change: dict) -> dict:
    """Yaw differences survive the similarity alignment unchanged, since both frames stand z up."""
    true_turn = _wrap(item["after"]["yaw_deg"] - item["before"]["yaw_deg"])
    if change.get("turn_deg") is None:
        return {"true_turn_deg": round(true_turn), "turn_reported": False}
    return {"true_turn_deg": round(true_turn), "turn_reported": True,
            "turn_error_deg": round(abs(_wrap(change["turn_deg"] - true_turn)))}


def _totals(rows: list[dict], scene: dict, scale: float, residual: np.ndarray) -> dict:
    found = [row for row in rows if row["found"]]
    return {
        "camera_alignment": {"scale": round(scale, 3),
                             "rmse_m": round(float(np.sqrt((residual ** 2).sum(axis=1).mean())), 3)},
        "recall": round(len(found) / max(len(rows), 1), 3),
        "precision": round(len(found) / max(len(scene["changes"]), 1), 3),
        "names_correct": sum(1 for row in found if row["name_ok"]),
        "mean_position_error_m": round(float(np.mean([row["position_error_m"] for row in found])), 3)
        if found else None,
        "changes": rows,
        "false_alarms": [c["id"] for c in scene["changes"] if c["id"] not in {row["found"] for row in found}],
    }


def evaluate(result_dir: Path, truth_path: Path) -> dict:
    scene = json.loads((result_dir / "scene.json").read_text())
    report = score(scene, json.loads(truth_path.read_text()))
    (result_dir / "evaluation.json").write_text(json.dumps(report, indent=1))
    return report
