"""The rules that decide what is reported, each on a scene small enough to reason about."""

import numpy as np
import pytest
from standardphysics_changes import language
from standardphysics_changes.evidence import GONE, KEPT, UNSEEN
from standardphysics_changes.export import frames_seeing_empty
from standardphysics_changes.geometry import Cloud
from standardphysics_changes.landmarks import Landmark, merge_touching
from standardphysics_changes.matching import consistent_turn, long_axis_deg
from standardphysics_changes.pictures import Sighting, runs_off_frame, touches_edge
from standardphysics_changes.pipeline import Scene, agree_on_kind, distinguish, empty_share, objects_only, regions_of
from standardphysics_changes.regions import Box, OneSidedRules, Region, RegionRules, fit_box, one_sided_regions
from test_change_geometry import camera_at, floor_and_box


def scene_with(points, status, through, agree, epoch, views=()):
    count = len(points)
    cloud = Cloud(points.astype(np.float32), np.zeros((count, 3), np.uint8), np.full(count, epoch, np.uint8))
    return Scene(list(views), cloud, status.astype(np.uint8), np.asarray(through), np.asarray(agree))


def test_a_region_needs_most_sightlines_into_it_to_see_empty_space():
    floor, box = floor_and_box()
    points = np.vstack([floor, box])
    status = np.concatenate([np.full(len(floor), KEPT), np.full(len(box), GONE)])
    through = np.concatenate([np.zeros(len(floor)), np.full(len(box), 9)])
    clear = scene_with(points, status, through, np.concatenate([np.full(len(floor), 5), np.full(len(box), 1)]), 0)
    murky = scene_with(points, status, through, np.concatenate([np.full(len(floor), 5), np.full(len(box), 4)]), 0)
    assert len(regions_of(clear, RegionRules(), 0.85)[0]) == 1
    assert regions_of(murky, RegionRules(), 0.85)[0] == []
    region = regions_of(clear, RegionRules(), 0.85)[0][0]
    assert empty_share(clear, region) == pytest.approx(0.9)


def test_frames_count_as_seeing_empty_space_only_when_most_of_the_spot_looks_empty():
    points = np.array([[x, y, 1.5] for x in np.linspace(-0.2, 0.2, 6) for y in np.linspace(-0.2, 0.2, 6)])
    looking = [camera_at([0, 0, 0], epoch=1) for _ in range(3)]
    elsewhere = camera_at([0, 0, 0], yaw=np.pi, epoch=1)
    scene = scene_with(points, np.full(len(points), GONE), np.zeros(len(points)), np.zeros(len(points)), 0,
                       [*looking, elsewhere])
    region = Region("removed", 0, np.arange(len(points)), Box(np.zeros(3), np.ones(3), 0.0), len(points))
    assert frames_seeing_empty(region, scene) == {"empty_in": 3, "of": 4, "video": "after"}


def test_furniture_sharing_a_name_takes_a_fitting_description_or_drops_out_of_sentences():
    def piece(name, detail, category="chair"):
        return Landmark(np.arange(1), Box(np.zeros(3), np.ones(3), 0.0), category, name, detail)

    leather, wall_crop, sofa = piece("chair", "brown leather chair"), piece("chair", "light grey wall"), piece(
        "sofa", "white sofa", "sofa")
    moved = Region("removed", 0, np.arange(1), Box(np.zeros(3), np.ones(3), 0.0), 1, names={"name": "armchair"})
    distinguish([leather, wall_crop, sofa], [moved])
    assert leather.name == "brown leather chair" and not leather.ambiguous
    assert wall_crop.ambiguous
    assert sofa.name == "sofa" and not sofa.ambiguous


def test_a_stray_piece_of_a_moved_chair_joins_the_move():
    from standardphysics_changes.matching import Move, absorb_fragments

    rng = np.random.default_rng(7)
    seat = rng.uniform([0.0, 0.0, 0.0], [0.5, 0.5, 0.8], (200, 3))
    legs = rng.uniform([0.5, 0.0, 0.0], [0.7, 0.5, 0.5], (100, 3))
    new = rng.uniform([3.0, 0.0, 0.0], [3.6, 0.5, 0.8], (200, 3))
    points = np.vstack([seat, legs, new])
    old = Region("removed", 0, np.arange(200), fit_box(seat), 200, names={"name": "plastic chair"})
    stray = Region("removed", 0, np.arange(200, 300), fit_box(legs), 100, names={"name": "white plastic chair"})
    box = Region("removed", 0, np.arange(200, 300), Box(np.array([9.0, 9.0, 0.2]), np.ones(3) * 0.4, 0.0), 100,
                 names={"name": "cardboard box"})
    after = Region("added", 1, np.arange(300, 500), fit_box(new), 200, names={"name": "plastic chair"})
    move = Move(old, after, 3.0, None, 1.0)
    loose_removed, loose_added = absorb_fragments([move], [stray, box], [], points)
    assert loose_removed == [box] and loose_added == []
    assert len(move.removed.point_ids) == 300


def test_a_piece_the_two_models_disagree_about_goes_unnamed():
    assert agree_on_kind("chair", "wooden chair")
    assert agree_on_kind("cabinet", "side table")
    assert agree_on_kind("table", "object")
    assert not agree_on_kind("chair", "nightstand")
    assert not agree_on_kind("shelf", "staircase")


def test_a_name_inside_a_longer_one_is_ambiguous():
    def piece(name, detail=""):
        return Landmark(np.arange(1), Box(np.zeros(3), np.ones(3), 0.0), "chair", name, detail)

    plain, wooden = piece("chair"), piece("wooden chair")
    distinguish([plain, wooden], [])
    assert plain.ambiguous
    assert not wooden.ambiguous


def test_a_surface_that_carries_on_past_the_frame_edge_runs_off_frame():
    view = camera_at([0, 0, 0])
    mask = np.zeros(view.shape, dtype=bool)
    mask[20:40, 70:80] = True
    sighting = Sighting(view, mask, 200, 1.0)
    assert runs_off_frame(sighting)
    view.depth[:, 78:] = 5.0
    assert not runs_off_frame(sighting)


def test_an_elongated_object_keeps_a_turn_only_when_its_long_side_agrees():
    before = Box(np.zeros(3), np.array([1.0, 0.6, 0.6]), 0.0)
    quarter = Box(np.zeros(3), np.array([1.0, 0.6, 0.6]), np.pi / 2)
    assert long_axis_deg(before) == pytest.approx(0.0)
    assert consistent_turn(90.0, before, quarter) == 90.0
    assert consistent_turn(-90.0, before, quarter) == -90.0
    assert consistent_turn(-60.0, before, quarter) is None
    square = Box(np.zeros(3), np.array([0.8, 0.75, 1.0]), 0.0)
    assert consistent_turn(165.0, square, square) == 165.0


def test_two_chairs_side_by_side_stay_two_chairs():
    rng = np.random.default_rng(5)
    left = rng.uniform([0.0, 0.0, 0.0], [0.7, 0.5, 0.9], (300, 3))
    right = rng.uniform([0.8, 0.0, 0.0], [1.5, 0.5, 0.9], (300, 3))
    points = np.vstack([left, right])
    first = Landmark(np.arange(300), fit_box(left), "chair", "chair")
    second = Landmark(np.arange(300, 600), fit_box(right), "chair", "chair")
    assert len(merge_touching([first, second], points)) == 2


def test_without_a_vision_model_every_seen_once_clump_is_kept():
    def clump(name):
        return Region("unchecked", 1, np.arange(1), Box(np.zeros(3), np.ones(3), 0.0), 1, names={"name": name})

    clumps = [clump("object"), clump("wall section"), clump("black pillar"), clump("plastic crate"), clump("glass vase"),
              clump("counter stool"), clump("bar counter"), clump("person")]
    assert len(objects_only(clumps, named_by_model=False)) == 8
    kept = [c.names["name"] for c in objects_only(clumps, named_by_model=True)]
    assert kept == ["object", "plastic crate", "glass vase", "counter stool"]


def test_a_region_cut_by_the_frame_edge_says_it_was_only_partly_seen():
    mask = np.zeros((100, 140), dtype=bool)
    mask[40:60, 50:80] = True
    assert not touches_edge(mask)
    mask[40:60, 130:140] = True
    assert touches_edge(mask)
    assert language.partly_seen("The wooden crate is gone.") == (
        "The wooden crate is gone; only part of it was ever in view, so it may be larger."
    )


def test_only_an_object_in_an_unchecked_part_of_the_room_is_listed_as_seen_once():
    floor, box = floor_and_box(box_centre=(2.0, 2.0))
    _, sofa_back = floor_and_box(box_centre=(0.0, 0.0), box_size=(0.4, 0.4, 0.5))
    _, sofa = floor_and_box(box_centre=(0.0, 0.42), box_size=(0.4, 0.4, 0.5))
    points = np.vstack([floor, box, sofa_back, sofa])
    status = np.concatenate([np.full(len(floor), KEPT), np.full(len(box), UNSEEN), np.full(len(sofa_back), UNSEEN),
                             np.full(len(sofa), KEPT)])
    found = one_sided_regions(points, status, 1, 2.2, OneSidedRules(min_points=100))
    assert len(found) == 1
    assert np.allclose(found[0].box.center[:2], [2.0, 2.0], atol=0.05)


def test_a_seat_that_lost_its_legs_borrows_the_height_of_its_other_end():
    from standardphysics_changes.matching import Move, match_heights

    standing = Region("removed", 0, np.arange(1), Box(np.array([0.0, 0.0, 0.25]), np.array([0.4, 0.4, 0.5]), 0.0), 1)
    seat = Region("added", 1, np.arange(1), Box(np.array([2.0, 0.0, 0.45]), np.array([0.4, 0.4, 0.1]), 0.0), 1)
    lifted = Region("added", 1, np.arange(1), Box(np.array([2.0, 0.0, 1.0]), np.array([0.4, 0.4, 0.5]), 0.0), 1)
    match_heights([Move(standing, seat, 2.0, None, 1.0), Move(standing, lifted, 2.0, None, 1.0)])
    assert seat.box.size[2] == pytest.approx(0.5) and seat.box.center[2] == pytest.approx(0.25)
    assert lifted.box.center[2] == pytest.approx(1.0)
