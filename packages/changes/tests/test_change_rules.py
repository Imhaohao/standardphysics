"""The rules that decide what is reported, each on a scene small enough to reason about."""

import numpy as np
import pytest
from standardphysics_changes.evidence import GONE, KEPT, UNSEEN
from standardphysics_changes.export import frames_seeing_empty
from standardphysics_changes.geometry import Cloud
from standardphysics_changes.landmarks import Landmark
from standardphysics_changes.matching import consistent_turn, long_axis_deg
from standardphysics_changes.pipeline import Scene, distinguish, empty_share, regions_of
from standardphysics_changes.regions import Box, OneSidedRules, Region, RegionRules, one_sided_regions
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


def test_an_elongated_object_keeps_a_turn_only_when_its_long_side_agrees():
    before = Box(np.zeros(3), np.array([1.0, 0.6, 0.6]), 0.0)
    quarter = Box(np.zeros(3), np.array([1.0, 0.6, 0.6]), np.pi / 2)
    assert long_axis_deg(before) == pytest.approx(0.0)
    assert consistent_turn(90.0, before, quarter) == 90.0
    assert consistent_turn(-90.0, before, quarter) == -90.0
    assert consistent_turn(-60.0, before, quarter) is None
    square = Box(np.zeros(3), np.array([0.8, 0.75, 1.0]), 0.0)
    assert consistent_turn(165.0, square, square) == 165.0


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
