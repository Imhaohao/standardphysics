"""The checked-in example results, scored against the rendered rooms' truth on every run.

Regenerating an example with a worse detector fails here, and so does a sentence that
stops agreeing with the numbers beside it.
"""

import json
import pathlib

import pytest
from standardphysics_changes import language
from standardphysics_changes.evaluate import score
from standardphysics_changes.export import detector_fingerprint

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESULTS = ROOT / "apps" / "web" / "public" / "changes"
TRUTH = ROOT / "datasets" / "changes"

# room, changes found with a box covering the object, changes only partly found, things listed as seen once,
# and reports of changes that did not happen, which are known misses kept visible rather than tuned away
EXPECTED = [
    ("living-room", 5, 0, 0, 0),
    ("studio", 4, 1, 0, 0),
    ("living-room-same", 0, 0, 0, 0),
    ("living-room-blind-spot", 1, 0, 1, 0),
    ("office", 3, 1, 0, 0),
    ("bedroom", 5, 0, 0, 1),
    ("kitchen", 5, 0, 0, 0),
]
# room, names that match the object exactly, names whose kind of thing is right, and which changes admit being partly seen
NAMES_AND_HEDGES = [
    ("living-room", "5 of 5", "5 of 5", []),
    ("studio", "3 of 4", "4 of 4", ["wooden crate"]),
    ("living-room-blind-spot", "1 of 1", "1 of 1", []),
    ("office", "1 of 3", "3 of 3", ["wooden crate"]),
    ("bedroom", "1 of 5", "2 of 5", []),
    ("kitchen", "1 of 5", "4 of 5", []),
]
# furniture the sentences may cite that stands on no real object: the kitchen's stove read as a white plastic chair
KNOWN_PHANTOMS = {"kitchen": ["white plastic chair"]}


def scored(room: str) -> tuple[dict, dict]:
    scene = json.loads((RESULTS / room / "scene.json").read_text())
    return scene, score(scene, json.loads((TRUTH / room / "truth.json").read_text()))


@pytest.mark.parametrize(("room", "found", "partial", "seen_once", "false_alarms"), EXPECTED)
def test_each_example_finds_its_changes_and_nothing_else(room, found, partial, seen_once, false_alarms):
    scene, report = scored(room)
    assert sum(1 for row in report["changes"] if row["found"]) == found
    assert len(report["partial"]) == partial
    assert len(report["false_alarms"]) == false_alarms
    assert report["unverifiable_reported"] == []
    assert len(scene["unchecked"]) == seen_once
    assert report["seen_once_on_unchanged"] == []
    assert len(report["unverifiable_listed"]) == len(json.loads((TRUTH / room / "truth.json").read_text())["unverifiable"])


@pytest.mark.parametrize(("room", "names", "kinds", "hedged"), NAMES_AND_HEDGES)
def test_names_stay_right_and_only_partly_seen_changes_say_so(room, names, kinds, hedged):
    scene, report = scored(room)
    assert report["names_correct"] == names
    assert report["head_nouns_correct"] == kinds
    rows = {row.get("found") or row.get("partial"): row["truth"] for row in report["changes"]}
    assert sorted(rows[change["id"]] for change in scene["changes"] if change["partly_seen"]) == sorted(hedged)


def test_every_checked_in_result_came_from_this_detector():
    made_by = {json.loads((RESULTS / room / "scene.json").read_text())["detector"] for room, *_ in EXPECTED}
    assert made_by == {detector_fingerprint()}


@pytest.mark.parametrize("room", [room for room, *_ in EXPECTED])
def test_furniture_the_sentences_can_cite_is_real_apart_from_known_misses(room):
    _, report = scored(room)
    assert report["phantom_furniture"] == KNOWN_PHANTOMS.get(room, [])


@pytest.mark.parametrize("room", ["living-room", "studio", "living-room-blind-spot", "office"])
def test_boxes_stand_on_what_holds_them_up(room):
    _, report = scored(room)
    assert report["mean_bottom_error_m"] < 0.05
    assert report["mean_height_error_m"] < 0.1


@pytest.mark.parametrize("room", [room for room, *_ in EXPECTED])
def test_sentences_carry_the_numbers_beside_them(room):
    scene, _ = scored(room)
    for change in scene["changes"]:
        if change["type"] == "moved":
            assert f"moved {language.length(change['distance_m'])}" in change["sentence"]
    assert scene["summary"] == language.summary(scene["changes"])
