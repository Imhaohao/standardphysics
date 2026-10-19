"""Labelling runs beside discovery, and its names land on discovery's graph afterwards.

The scan is a real one. Only the two passes' answers are stood in for, so the
rule for combining them is what is under test.
"""

import json

from standardphysics_pipeline.ingest import parse_room_json

from conftest import REPO
from standardphysics_api.stages import with_labels_from

PHONE = REPO / "datasets/phone/test1"


def _scan():
    return parse_room_json(json.loads((PHONE / "room.json").read_text()))


def _contents(graph):
    return [node for node in graph.nodes if node.movable]


def _relabelled(graph, by, label, movable=None):
    def changed(node):
        update = {"label": f"{label} {node.label}", "labeled_by": by}
        if movable is not None:
            update["movable"] = movable
        return node.model_copy(update=update)

    return graph.model_copy(update={"nodes": [changed(node) for node in graph.nodes]})


def test_labelling_names_every_piece_discovery_left_alone():
    scan = _scan()
    labelled = _relabelled(scan, "astra", "named")
    combined = with_labels_from(scan, labelled)
    assert [node.label for node in combined.nodes] == [node.label for node in labelled.nodes]
    assert all(node.labeled_by == "astra" for node in combined.nodes)


def test_a_name_discovery_gave_from_the_photos_keeps_the_last_word():
    scan = _scan()
    piece = _contents(scan)[0]
    found = scan.model_copy(update={"nodes": [
        node.model_copy(update={"label": "Counter", "labeled_by": "discovery"}) if node.id == piece.id else node
        for node in scan.nodes
    ]})
    combined = {node.id: node for node in with_labels_from(found, _relabelled(scan, "astra", "named")).nodes}
    assert combined[piece.id].label == "Counter"
    assert combined[piece.id].labeled_by == "discovery"


def test_either_pass_can_pin_a_piece_in_place():
    scan = _scan()
    pinned_by_labelling = with_labels_from(scan, _relabelled(scan, "astra", "named", movable=False))
    assert not any(node.movable for node in pinned_by_labelling.nodes)
    pinned_by_discovery = with_labels_from(
        scan.model_copy(update={"nodes": [node.model_copy(update={"movable": False}) for node in scan.nodes]}),
        _relabelled(scan, "astra", "named", movable=True),
    )
    assert not any(node.movable for node in pinned_by_discovery.nodes)


def test_geometry_stays_as_discovery_measured_it():
    scan = _scan()
    combined = with_labels_from(scan, _relabelled(scan, "astra", "named"))
    assert [(node.transform, node.dimensions) for node in combined.nodes] == [
        (node.transform, node.dimensions) for node in scan.nodes
    ]
