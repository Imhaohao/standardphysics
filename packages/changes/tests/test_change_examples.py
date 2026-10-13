"""The checked-in example results, scored against the rendered rooms' truth on every run.

Regenerating an example with a worse detector fails here, and so does a sentence that
stops agreeing with the numbers beside it.
"""

import json
import pathlib

import pytest
from standardphysics_changes import language
from standardphysics_changes.evaluate import score

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESULTS = ROOT / "apps" / "web" / "public" / "changes"
TRUTH = ROOT / "datasets" / "changes"

# room, changes it must find, how many it may report at most
EXPECTED = [
    ("living-room", 5, 5),
    ("studio", 5, 5),
    ("living-room-same", 0, 0),
    ("living-room-blind-spot", 1, 1),
]


def scored(room: str) -> tuple[dict, dict]:
    scene = json.loads((RESULTS / room / "scene.json").read_text())
    return scene, score(scene, json.loads((TRUTH / room / "truth.json").read_text()))


@pytest.mark.parametrize(("room", "must_find", "may_report"), EXPECTED)
def test_each_example_finds_its_changes_and_nothing_else(room, must_find, may_report):
    scene, report = scored(room)
    assert sum(1 for row in report["changes"] if row["found"]) == must_find
    assert len(scene["changes"]) <= may_report
    assert report["false_alarms"] == []
    assert report["unverifiable_reported"] == []


@pytest.mark.parametrize("room", ["living-room", "studio", "living-room-blind-spot"])
def test_boxes_stand_on_what_holds_them_up(room):
    _, report = scored(room)
    assert report["mean_bottom_error_m"] < 0.05
    assert report["mean_height_error_m"] < 0.1


@pytest.mark.parametrize("room", [room for room, _, _ in EXPECTED])
def test_sentences_carry_the_numbers_beside_them(room):
    scene, _ = scored(room)
    for change in scene["changes"]:
        if change["type"] == "moved":
            assert f"moved {language.length(change['distance_m'])}" in change["sentence"]
    assert scene["summary"] == language.summary(scene["changes"])
