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

# room, changes found with a box covering the object, changes only partly found, things listed as seen once
EXPECTED = [
    ("living-room", 5, 0, 0),
    ("studio", 4, 1, 0),
    ("living-room-same", 0, 0, 0),
    ("living-room-blind-spot", 1, 0, 1),
]


def scored(room: str) -> tuple[dict, dict]:
    scene = json.loads((RESULTS / room / "scene.json").read_text())
    return scene, score(scene, json.loads((TRUTH / room / "truth.json").read_text()))


@pytest.mark.parametrize(("room", "found", "partial", "seen_once"), EXPECTED)
def test_each_example_finds_its_changes_and_nothing_else(room, found, partial, seen_once):
    scene, report = scored(room)
    assert sum(1 for row in report["changes"] if row["found"]) == found
    assert len(report["partial"]) == partial
    assert report["false_alarms"] == []
    assert report["unverifiable_reported"] == []
    assert len(scene["unchecked"]) == seen_once
    assert len(report["unverifiable_listed"]) == len(json.loads((TRUTH / room / "truth.json").read_text())["unverifiable"])


@pytest.mark.parametrize("room", ["living-room", "studio", "living-room-blind-spot"])
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
