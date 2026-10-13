"""Locations measured against the furniture that stayed put."""

import numpy as np
from standardphysics_changes.landmarks import (
    Landmark,
    apart_from,
    crossed,
    footprint_gap,
    heading,
    merge_touching,
    place_phrase,
    vote_classes,
)
from standardphysics_changes.regions import Box
from test_change_geometry import camera_at


def piece(name, centre, size, yaw=0.0):
    return Landmark(np.arange(1), Box(np.array(centre, float), np.array(size, float), yaw), name, name)


SOFA = piece("sofa", (0, 2, 0.4), (2.0, 0.9, 0.8))
TABLE = piece("coffee table", (0, 0.8, 0.2), (1.2, 0.6, 0.4))
SHELF = piece("bookshelf", (-2.3, 0.5, 1.0), (0.3, 1.0, 2.0))


def test_footprint_gap_is_floor_distance_between_boxes():
    assert abs(footprint_gap(SOFA.box, TABLE.box) - 0.45) < 1e-6
    overlapping = Box(np.array([0.2, 0.8, 0.2]), np.array([0.4, 0.4, 0.4]), 0.0)
    assert footprint_gap(overlapping, TABLE.box) == 0.0


def test_a_thing_resting_on_the_table_is_on_it():
    basket = Box(np.array([0.2, 0.8, 0.52]), np.array([0.4, 0.3, 0.24]), 0.3)
    assert place_phrase(basket, [SOFA, TABLE, SHELF]) == "on the coffee table"


def test_a_thing_on_the_floor_takes_the_nearest_furniture():
    box = Box(np.array([-1.6, 0.5, 0.3]), np.array([0.5, 0.5, 0.6]), 0.0)
    assert place_phrase(box, [SOFA, TABLE, SHELF]) == "between the bookshelf and the coffee table"
    lonely = Box(np.array([3.5, -2.0, 0.3]), np.array([0.5, 0.5, 0.6]), 0.0)
    assert place_phrase(lonely, [SOFA, TABLE, SHELF]) == "on the open floor"
    close = Box(np.array([1.3, 2.0, 0.3]), np.array([0.4, 0.4, 0.6]), 0.0)
    assert place_phrase(close, [SOFA]) == "beside the sofa"


def test_moves_name_what_they_passed_and_where_they_went():
    start, end = np.array([-1.5, 0.8, 0.4]), np.array([1.6, 0.8, 0.4])
    assert crossed([SOFA, TABLE, SHELF], start, end) == "coffee table"
    assert heading([SOFA, TABLE, SHELF], np.array([2.0, 0.5, 0.3]), np.array([0.0, 0.5, 0.3])) == "bookshelf"


def test_a_piece_inside_a_larger_one_merges_into_it():
    rng = np.random.default_rng(0)
    table = rng.uniform([-0.3, -0.3, 0], [0.3, 0.3, 0.6], (400, 3))
    sofa = rng.uniform([0.35, -0.3, 0], [2.35, 0.7, 0.8], (50, 3))
    points = np.vstack([table, sofa])
    big = Landmark(np.arange(300), Box(np.array([0, 0, 0.3]), np.array([0.6, 0.6, 0.6]), 0.0), "table")
    inner = Landmark(np.arange(300, 400), Box(np.array([0.2, 0, 0.3]), np.array([0.2, 0.2, 0.3]), 0.0), "cabinet")
    beside = Landmark(np.arange(400, 450), Box(np.array([1.35, 0.2, 0.4]), np.array([2.0, 1.0, 0.8]), 0.0), "sofa")
    merged = merge_touching([inner, big, beside], points)
    assert [m.category for m in merged] == ["table", "sofa"]
    assert len(merged[0].point_ids) == 400


def test_leftovers_of_a_change_are_not_furniture_but_the_table_under_it_is():
    plant_left = piece("plant", (-0.3, 4.0, 0.8), (0.7, 0.6, 1.0))
    removed_plant = Box(np.array([0.0, 3.7, 0.75]), np.array([0.6, 0.6, 1.3]), np.radians(40))
    basket = Box(np.array([0.2, 0.8, 0.52]), np.array([0.4, 0.3, 0.24]), 0.0)
    points = np.zeros((1, 3))
    kept = apart_from([plant_left, TABLE, SOFA], points, [removed_plant, basket])
    assert [lm.name for lm in kept] == ["coffee table", "sofa"]


def test_pixel_labels_vote_onto_the_points_they_see():
    view = camera_at([0, 0, 0])
    classes = np.full(view.shape, 7, dtype=np.int16)
    classes[:, :40] = 3
    points = np.array([[-0.5, 0.0, 3.0], [0.5, 0.0, 3.0], [0.0, 0.0, 1.0]])
    assert vote_classes(points, [view, view], [classes, classes]).tolist() == [3, 7, -1]
