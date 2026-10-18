"""Pieces cut from the mesh, held to what the real phone scans measured.

No room is built here. RoomPlan's own boxes are the only reference, and only the
ones with volume: the things it measured as solid. Their names are never read.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest
from standardphysics_pipeline.ingest import parse_room_json
from standardphysics_pipeline.substrate import extent_along, gravity, overlap_fraction, regions, volume
from standardphysics_pipeline.substrate.segment import segment

ROOT = pathlib.Path(__file__).resolve().parents[3]
PHONE = ROOT / "datasets/phone"

MOSTLY = 0.8
"""Share of a piece that must lie in a box for the box to be said to hold it."""

STRADDLING = (0.2, 0.8)
"""A piece with between these shares inside a box was cut across that box's edge."""


def _scans():
    return [
        directory
        for directory in sorted(PHONE.glob("*"))
        if (directory / "room.json").is_file() and (directory / "lidar-mesh.json").is_file()
    ]


@pytest.fixture(scope="module")
def cut():
    found = _scans()
    if not found:
        pytest.skip("no scanned room with a mesh on this machine")
    out = []
    for directory in found:
        graph = parse_room_json(json.loads((directory / "room.json").read_text()))
        solid = [box for box in regions(graph) if volume(box) > 0]
        out.append((directory.name, graph, solid, segment(directory / "lidar-mesh.json", graph.capture_to_room)))
    return out


def _share_in_any(piece, boxes) -> float:
    return max((overlap_fraction(piece, box) for box in boxes), default=0.0)


class TestPiecesComeOutOfTheMesh:
    def test_every_scan_is_cut_into_many_pieces(self, cut):
        for name, _graph, solid, pieces in cut:
            assert len(pieces) > 10 * len(solid), name

    def test_every_piece_has_measured_extent(self, cut):
        for name, _graph, _solid, pieces in cut:
            for piece in pieces:
                assert np.all(piece.extents >= 0), name
                assert piece.extents.max() > 0, name

    def test_no_piece_is_the_size_of_the_room(self, cut):
        """A phone mesh is one continuous skin, so a cut that only follows touching
        gives back the whole room as one piece. Only flat sheets may span metres."""
        for name, _graph, _solid, pieces in cut:
            for piece in pieces:
                assert np.sort(piece.extents)[0] < 0.5 or np.sort(piece.extents)[1] < 2.5, name


class TestPiecesFollowWhatWasMeasured:
    def test_pieces_are_rarely_cut_across_a_solid_box(self, cut):
        for name, _graph, solid, pieces in cut:
            shares = [_share_in_any(piece, solid) for piece in pieces]
            straddling = sum(STRADDLING[0] < share < STRADDLING[1] for share in shares)
            assert straddling / len(pieces) < 0.06, f"{name}: {straddling} of {len(pieces)}"

    def test_nearly_every_solid_box_holds_a_piece_of_its_own(self, cut):
        for name, _graph, solid, pieces in cut:
            held = sum(any(overlap_fraction(piece, box) > MOSTLY for piece in pieces) for box in solid)
            assert held >= 0.9 * len(solid), f"{name}: {held} of {len(solid)}"

    def test_the_mesh_holds_things_no_box_was_drawn_around(self, cut):
        """The reason this layer exists: measured matter the scanner never boxed."""
        for name, graph, solid, pieces in cut:
            up = -gravity(graph)
            lowest = min(extent_along(piece, up)[0] for piece in pieces)
            unboxed = [
                piece
                for piece in pieces
                if _share_in_any(piece, solid) < 0.05 and extent_along(piece, up)[0] > lowest + 0.1
            ]
            assert len(unboxed) >= 100, f"{name}: {len(unboxed)}"


class TestPiecesKeepTheirIds:
    def test_the_same_mesh_gives_the_same_ids(self, cut):
        for name, graph, _solid, pieces in cut:
            again = segment(PHONE / name / "lidar-mesh.json", graph.capture_to_room)
            assert [piece.id for piece in again] == [piece.id for piece in pieces], name

    def test_no_two_pieces_share_an_id(self, cut):
        for name, _graph, _solid, pieces in cut:
            assert len({piece.id for piece in pieces}) == len(pieces), name
