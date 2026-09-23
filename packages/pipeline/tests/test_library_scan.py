"""Several rooms made into one floor: the indices, the frames, and what coverage counts.

None of this needs Blender or a stored capture, so the rooms here are a few triangles
built in place with colours chosen to be told apart by eye.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
from standardphysics_pipeline.textures import library_scan
from standardphysics_pipeline.textures.library_scan import (
    LibraryPaint,
    RoomCapture,
    moved_to_floor,
    paint_the_rooms,
    rooms_concatenated,
    unobserved_filled_from_nearest,
)
from standardphysics_pipeline.textures.scan_colour import UNSEEN, ColouredScan


def square(corner=(0.0, 0.0, 0.0), colour=(0.2, 0.6, 0.9), seen=True) -> ColouredScan:
    """A unit square on the floor as two triangles, every vertex the same colour."""
    offsets = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    return ColouredScan(
        vertices=np.asarray(corner, dtype=np.float64) + offsets,
        triangles=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        colours=np.tile(np.asarray(colour, dtype=np.float32), (4, 1)),
        seen=np.full(4, seen),
    )


def shifted(x=0.0, y=0.0, z=0.0) -> np.ndarray:
    matrix = np.eye(4)
    matrix[:3, 3] = (x, y, z)
    return matrix


def turned_a_quarter_turn() -> np.ndarray:
    """A 90 degree rotation about z, which sends +x to +y."""
    matrix = np.eye(4)
    matrix[:2, :2] = [[0.0, -1.0], [1.0, 0.0]]
    return matrix


class TestMerging:
    def test_each_room_triangle_still_names_its_own_corners(self):
        first, second = square(), square(corner=(5.0, 0.0, 0.0))
        merged = rooms_concatenated([first, second])
        assert np.allclose(merged.vertices[merged.triangles[:2]], first.vertices[first.triangles])
        assert np.allclose(merged.vertices[merged.triangles[2:]], second.vertices[second.triangles])

    def test_the_second_room_is_offset_by_the_first_rooms_vertex_count(self):
        merged = rooms_concatenated([square(), square(corner=(5.0, 0.0, 0.0))])
        assert merged.triangles[:2].max() == 3
        assert merged.triangles[2:].min() == 4
        assert merged.triangles.max() == len(merged.vertices) - 1

    def test_colours_and_coverage_stay_with_their_own_vertices(self):
        merged = rooms_concatenated([
            square(colour=(1.0, 0.0, 0.0), seen=True),
            square(corner=(5.0, 0.0, 0.0), colour=(0.0, 0.0, 1.0), seen=False),
        ])
        assert merged.colours[:4] == pytest.approx(np.tile((1.0, 0.0, 0.0), (4, 1)))
        assert merged.colours[4:] == pytest.approx(np.tile((0.0, 0.0, 1.0), (4, 1)))
        assert merged.seen.tolist() == [True] * 4 + [False] * 4

    def test_overlapping_rooms_are_kept_twice_rather_than_welded(self):
        """Two captures of the same square metre stay two square metres of geometry."""
        merged = rooms_concatenated([square(), square()])
        assert len(merged.vertices) == 8
        assert len(merged.triangles) == 4

    def test_merging_nothing_says_so(self):
        with pytest.raises(ValueError):
            rooms_concatenated([])


class TestMovingOntoTheFloor:
    def test_a_translation_reaches_the_vertices(self):
        moved = moved_to_floor(square(), shifted(x=3.0, z=-1.0))
        assert moved.vertices[0] == pytest.approx([3.0, 0.0, -1.0])
        assert moved.vertices[1] == pytest.approx([4.0, 0.0, -1.0])

    def test_a_rotation_reaches_the_vertices(self):
        moved = moved_to_floor(square(), turned_a_quarter_turn())
        assert moved.vertices[1] == pytest.approx([0.0, 1.0, 0.0])

    def test_nothing_but_the_vertices_moves(self):
        room = square()
        moved = moved_to_floor(room, shifted(y=2.0))
        assert np.array_equal(moved.triangles, room.triangles)
        assert np.array_equal(moved.colours, room.colours)
        assert np.array_equal(moved.seen, room.seen)


def half_observed_room() -> ColouredScan:
    """One square a camera saw, one it did not, the unobserved one left at the scan grey."""
    observed = square(colour=(1.0, 0.0, 0.0), seen=True)
    unobserved = square(corner=(0.0, 0.0, 0.5), colour=UNSEEN, seen=False)
    return rooms_concatenated([observed, unobserved])


class TestFillingTheGaps:
    def test_an_unobserved_vertex_takes_the_nearest_observed_colour(self):
        filled = unobserved_filled_from_nearest(half_observed_room())
        assert filled.colours[4:] == pytest.approx(np.tile((1.0, 0.0, 0.0), (4, 1)))
        assert not np.isclose(filled.colours, UNSEEN).all(axis=1).any()

    def test_filling_does_not_claim_the_vertex_was_measured(self):
        room = half_observed_room()
        filled = unobserved_filled_from_nearest(room)
        assert np.array_equal(filled.seen, room.seen)
        assert filled.painted_fraction == 0.5

    def test_an_observed_vertex_keeps_what_the_camera_gave_it(self):
        room = half_observed_room()
        filled = unobserved_filled_from_nearest(room)
        assert np.array_equal(filled.colours[:4], room.colours[:4])

    def test_a_room_no_camera_reached_is_left_alone(self):
        room = square(colour=UNSEEN, seen=False)
        assert unobserved_filled_from_nearest(room) is room

    def test_a_fully_observed_room_is_left_alone(self):
        room = square()
        assert unobserved_filled_from_nearest(room) is room


def room_called(name: str) -> RoomCapture:
    return RoomCapture(
        name=name,
        mesh_path=pathlib.Path(f"{name}/lidar-mesh.json"),
        poses_path=pathlib.Path(f"{name}/poses.json"),
        frame_paths={},
        capture_to_room=None,
        to_floor=np.eye(4),
    )


class TestPaintingEveryRoom:
    """The assembly, with the painting and the Blender write stood in for."""

    @pytest.fixture
    def painted_pretend_rooms(self, monkeypatch, tmp_path):
        written: list[ColouredScan] = []
        rooms = {
            "seen": (square(seen=True), 12),
            "unseen": (square(corner=(5.0, 0.0, 0.0), colour=UNSEEN, seen=False), 8),
        }

        def remember_instead_of_calling_blender(scan, out_path, max_triangles=None):
            written.append(scan)
            return out_path

        monkeypatch.setattr(library_scan, "painted_room", lambda room: rooms[room.name])
        monkeypatch.setattr(library_scan, "write_scan_glb", remember_instead_of_calling_blender)
        paint = paint_the_rooms([room_called(name) for name in rooms], tmp_path / "floor.glb")
        return paint, written

    def test_it_reports_what_the_cameras_measured_and_not_what_was_filled(self, painted_pretend_rooms):
        paint, _ = painted_pretend_rooms
        assert paint.directly_observed_fraction == 0.5

    def test_it_counts_the_merged_geometry_and_the_photos_behind_it(self, painted_pretend_rooms):
        paint, _ = painted_pretend_rooms
        assert isinstance(paint, LibraryPaint)
        assert (paint.vertices, paint.triangles, paint.photos_used) == (8, 4, 20)
        assert paint.seconds >= 0.0

    def test_the_merged_floor_is_what_gets_written(self, painted_pretend_rooms, tmp_path):
        paint, written = painted_pretend_rooms
        assert paint.glb_path == tmp_path / "floor.glb"
        assert len(written) == 1
        assert written[0].triangles.max() == len(written[0].vertices) - 1
