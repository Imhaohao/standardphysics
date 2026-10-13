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

# room, changes found with a box covering the object, changes only partly found, things listed as not counted,
# and reports of changes that did not happen, which are known misses kept visible rather than tuned away
EXPECTED = [
    ("living-room", 4, 0, 1, 0),
    ("studio", 4, 0, 0, 1),
    ("living-room-same", 0, 0, 0, 0),
    ("living-room-blind-spot", 1, 0, 1, 0),
    ("office", 3, 0, 0, 0),
    ("bedroom", 4, 0, 1, 0),
    ("kitchen", 5, 0, 0, 0),
    ("workshop", 5, 0, 1, 0),
    ("lounge", 4, 0, 0, 0),
    ("study", 3, 1, 0, 0),
]
# room, names that match the object exactly, names whose kind of thing is right, and which changes admit being partly seen
NAMES_AND_HEDGES = [
    ("living-room", "4 of 4", "4 of 4", []),
    ("studio", "3 of 4", "4 of 4", []),
    ("living-room-blind-spot", "1 of 1", "1 of 1", []),
    ("office", "1 of 3", "2 of 3", []),
    ("bedroom", "1 of 4", "1 of 4", []),
    ("kitchen", "1 of 5", "4 of 5", []),
    ("workshop", "4 of 5", "5 of 5", []),
    ("lounge", "1 of 4", "2 of 4", []),
    ("study", "2 of 3", "3 of 3", []),
]
# furniture that stands on no real object: part of the kitchen's white stove, which both models took for a chair
KNOWN_PHANTOMS = {"kitchen": ["white chair"]}
# real changes set aside as hanging in the air: the living room's basket on the coffee table, whose support
# test found unchanged table top under only 54% of its footprint against the 75% it needs
KNOWN_SET_ASIDE = {"living-room": ["u1 set aside a real change"]}


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
    assert report["seen_once_on_nothing"] == []
    assert len(report["unverifiable_listed"]) == len(json.loads((TRUTH / room / "truth.json").read_text())["unverifiable"])


@pytest.mark.parametrize(("room", "names", "kinds", "hedged"), NAMES_AND_HEDGES)
def test_names_stay_right_and_only_partly_seen_changes_say_so(room, names, kinds, hedged):
    scene, report = scored(room)
    assert report["names_correct"] == names
    assert report["head_nouns_correct"] == kinds
    rows = {row.get("found") or row.get("partial"): row["truth"] for row in report["changes"]}
    matched = [change for change in scene["changes"] if change["id"] in rows]
    assert sorted(rows[change["id"]] for change in matched if change["partly_seen"]) == sorted(hedged)


def test_every_checked_in_result_came_from_this_detector():
    made_by = {json.loads((RESULTS / room / "scene.json").read_text())["detector"] for room, *_ in EXPECTED}
    assert made_by == {detector_fingerprint()}


@pytest.mark.parametrize("room", [room for room, *_ in EXPECTED])
def test_nothing_set_aside_as_hanging_in_the_air_was_a_real_change_apart_from_known_misses(room):
    _, report = scored(room)
    assert report["doubted_real_changes"] == KNOWN_SET_ASIDE.get(room, [])


@pytest.mark.parametrize("room", [room for room, *_ in EXPECTED])
def test_furniture_the_sentences_can_cite_is_real_apart_from_known_misses(room):
    _, report = scored(room)
    assert report["phantom_furniture"] == KNOWN_PHANTOMS.get(room, [])


@pytest.mark.parametrize("room", ["living-room", "studio", "living-room-blind-spot", "office", "bedroom", "kitchen",
                                  "workshop", "study"])
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


def test_every_first_run_is_indexed_with_the_detector_that_made_it():
    held_out = pathlib.Path(__file__).resolve().parents[1] / "held-out"
    index = {entry["file"]: entry["detector"] for entry in json.loads((held_out / "index.json").read_text())["first_runs"]}
    saved = {path.name for path in held_out.glob("*.json")} - {"index.json"}
    assert set(index) == saved
    for name, detector in index.items():
        embedded = json.loads((held_out / name).read_text()).get("detector")
        assert embedded in (None, detector)
