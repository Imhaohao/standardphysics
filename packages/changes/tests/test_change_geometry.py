"""The change reasoning on scenes small enough to check by hand."""

import numpy as np
import pytest
from standardphysics_changes.evaluate import box_overlap, name_matches, umeyama
from standardphysics_changes.evidence import GONE, KEPT, UNSEEN, DepthLookup, Evidence, Tolerance, classify, gather
from standardphysics_changes.geometry import (
    Sampling,
    apply,
    backproject,
    fit_floor,
    project,
    room_frame,
    voxel_downsample,
)
from standardphysics_changes.matching import MatchRules, estimate_turn, pair_moves
from standardphysics_changes.pipeline import height_scale
from standardphysics_changes.regions import Box, RegionRules, find_regions, finish_regions, fit_box, settle
from standardphysics_changes.views import View


def camera_at(position, depth_value=3.0, size=(60, 80), yaw=0.0, epoch=1):
    """A camera looking along +z (turned by `yaw` about the vertical y axis) at a flat wall."""
    height, width = size
    c, s = np.cos(yaw), np.sin(yaw)
    pose = np.eye(4)
    pose[:3, :3] = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    pose[:3, 3] = position
    return View(
        epoch=epoch, frame_index=0, time_s=0.0, image=np.zeros((height, width, 3), np.uint8),
        detail=np.zeros((height * 2, width * 2, 3), np.uint8), depth=np.full(size, depth_value, np.float32),
        confidence=np.ones(size, np.float32), intrinsics=np.array([[50.0, 0, width / 2], [0, 50.0, height / 2],
                                                                   [0, 0, 1]]),
        cam_to_world=pose,
    )


def test_projection_inverts_backprojection():
    view = camera_at([0.2, -0.1, 0.0], yaw=0.3)
    points, _ = backproject(view, Sampling(stride=4, border_px=0))
    u, v, z = project(points, view)
    assert np.allclose(z, 3.0, atol=1e-4)
    assert u.min() >= 0 and u.max() <= 80 and v.min() >= 0 and v.max() <= 60


def test_the_other_video_seeing_past_a_point_means_it_is_gone():
    tolerance = Tolerance()
    lookups = [DepthLookup.of(camera_at([x, 0, 0]), tolerance) for x in (-0.1, 0.0, 0.1)]
    points = np.array([
        [0.0, 0.0, 1.5],   # in front of the wall: every camera sees through it
        [0.0, 0.0, 3.0],   # on the wall: every camera agrees
        [0.0, 0.0, 4.5],   # behind the wall: hidden, says nothing
        [9.0, 0.0, 3.0],   # outside every frame
    ])
    evidence = gather(points, lookups, tolerance)
    assert evidence.through.tolist() == [3, 0, 0, 0]
    assert evidence.agree.tolist() == [0, 3, 0, 0]
    assert evidence.blocked.tolist() == [0, 0, 3, 0]
    assert classify(evidence).tolist() == [GONE, KEPT, UNSEEN, UNSEEN]


def test_one_glimpse_through_a_point_is_not_enough():
    evidence = Evidence(agree=np.array([0, 1, 0]), through=np.array([1, 5, 4]), blocked=np.array([0, 0, 0]))
    assert classify(evidence).tolist() == [UNSEEN, GONE, GONE]
    mostly_seen = Evidence(agree=np.array([4]), through=np.array([2]), blocked=np.array([0]))
    assert classify(mostly_seen).tolist() == [KEPT]


def floor_and_box(box_centre=(1.0, 1.0), box_size=(0.4, 0.3, 0.5), spacing=0.02):
    xs = np.arange(-1, 3, spacing)
    floor = np.array([[x, y, 0.0] for x in xs for y in xs])
    grid = [np.arange(-s / 2, s / 2 + 1e-9, spacing) for s in box_size]
    shell = np.array([[x, y, z] for x in grid[0] for y in grid[1] for z in grid[2]
                      if min(abs(abs(x) - box_size[0] / 2), abs(abs(y) - box_size[1] / 2),
                             abs(abs(z) - box_size[2] / 2)) < spacing / 2])
    box = shell + [box_centre[0], box_centre[1], box_size[2] / 2 + 0.01]
    return floor, box


def test_a_vanished_box_becomes_one_region_with_its_size():
    floor, box = floor_and_box()
    speck = np.array([[2.5, 2.5, 0.3], [2.52, 2.5, 0.3]])
    points = np.vstack([floor, box, speck])
    status = np.concatenate([np.full(len(floor), KEPT), np.full(len(box), GONE), np.full(2, GONE)]).astype(np.uint8)
    regions = finish_regions(find_regions(points, status, "removed", 0), points)
    assert len(regions) == 1
    found = regions[0].box
    assert np.allclose(found.center[:2], [1.0, 1.0], atol=0.03)
    assert np.allclose(sorted(found.size[:2]), [0.3, 0.4], atol=0.05)
    assert found.size[2] == pytest.approx(0.5, abs=0.05)


def test_a_region_grows_into_unseen_points_but_not_into_kept_ones():
    floor, box = floor_and_box()
    status = np.full(len(box), GONE, dtype=np.uint8)
    status[box[:, 2] > 0.35] = UNSEEN
    points = np.vstack([floor, box])
    status = np.concatenate([np.full(len(floor), KEPT), status]).astype(np.uint8)
    regions = finish_regions(find_regions(points, status, "removed", 0, RegionRules()), points)
    assert len(regions) == 1
    assert regions[0].box.size[2] == pytest.approx(0.5, abs=0.06)


def test_box_fit_follows_a_turned_footprint():
    rng = np.random.default_rng(1)
    local = rng.uniform([-0.4, -0.15, 0], [0.4, 0.15, 0.6], size=(3000, 3))
    angle = np.radians(30)
    turn = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    box = fit_box(local @ turn.T + [2, 1, 0])
    assert np.degrees(box.yaw) % 90 == pytest.approx(30, abs=3)
    assert sorted(box.size[:2]) == pytest.approx([0.3, 0.8], abs=0.04)


def chair_shape():
    seat = np.array([[x, y, 0.45] for x in np.linspace(-0.3, 0.3, 15) for y in np.linspace(-0.3, 0.3, 15)])
    back = np.array([[x, 0.3, z] for x in np.linspace(-0.3, 0.3, 15) for z in np.linspace(0.45, 1.0, 12)])
    return np.vstack([seat, back])


def test_the_turn_of_a_moved_chair_comes_from_its_shape():
    chair = chair_shape()
    angle = np.radians(90)
    turn = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    assert estimate_turn(chair, chair @ turn.T + [2, 0, 0]) == pytest.approx(90, abs=5)


def test_a_shape_that_looks_the_same_turned_reports_no_turn():
    _, cube = floor_and_box(box_size=(0.4, 0.4, 0.4))
    angle = np.radians(30)
    turn = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    assert estimate_turn(cube, cube @ turn.T) is None


def test_matching_pairs_look_alikes_and_ignores_strangers():
    _, box = floor_and_box()
    _, tall = floor_and_box(box_centre=(1.0, 3.0), box_size=(0.4, 0.3, 1.5))
    points = np.vstack([box, box + [1.5, 0, 0], tall])
    third = len(box)
    status = np.full(len(points), GONE, dtype=np.uint8)
    removed = finish_regions(find_regions(points[:third], status[:third], "removed", 0), points[:third])
    added = finish_regions(find_regions(points, status, "added", 1), points)
    added = [r for r in added if r.box.center[0] > 2.0 or r.box.center[1] > 2.0]
    for region in removed + added:
        tall = region.box.size[2] > 1.0
        region.descriptor = np.array([0.0, 1.0]) if tall else np.array([1.0, 0.0])
    moves = pair_moves(removed, added, points, MatchRules())
    assert len(moves) == 1
    assert moves[0].distance_m == pytest.approx(1.5, abs=0.05)


def test_the_floor_is_the_lowest_broad_surface_not_a_tabletop():
    rng = np.random.default_rng(2)
    floor = np.column_stack([rng.uniform(-2, 2, (4000, 2)), rng.normal(0, 0.005, 4000)])
    table = np.column_stack([rng.uniform(0, 1, (3000, 2)), 0.75 + rng.normal(0, 0.005, 3000)])
    tilt = np.radians(10)
    rotation = np.array([[1, 0, 0], [0, np.cos(tilt), -np.sin(tilt)], [0, np.sin(tilt), np.cos(tilt)]])
    points = np.vstack([floor, table]) @ rotation.T + [0, 0, -1.4]
    normal, height = fit_floor(points, np.array([0.0, 0.0, 1.0]))
    assert normal @ (rotation @ [0, 0, 1]) == pytest.approx(1.0, abs=1e-3)
    assert height == pytest.approx(-1.4 * np.cos(tilt), abs=0.02)


def test_room_frame_stands_the_floor_at_zero():
    rng = np.random.default_rng(3)
    floor = np.column_stack([rng.uniform(-2, 2, (5000, 2)), np.zeros(5000)])
    wall = np.column_stack([rng.uniform(-2, 2, 3000), np.full(3000, 2.0), rng.uniform(0, 2.5, 3000)])
    camera = camera_at([0, 0, 0], epoch=0)
    camera.cam_to_world[:3, :3] = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]
    camera.cam_to_world[:3, 3] = [0, 0, 1.5]
    transform = room_frame([camera], np.vstack([floor, wall]))
    moved = apply(transform, floor)
    assert np.abs(moved[:, 2]).max() < 0.02


def test_voxels_average_their_points():
    points = np.array([[0.01, 0.01, 0.01], [0.03, 0.01, 0.01], [0.5, 0.5, 0.5]], dtype=np.float32)
    colors = np.array([[0, 0, 0], [200, 100, 50], [10, 10, 10]], dtype=np.uint8)
    merged, merged_colors = voxel_downsample(points, colors, 0.1)
    assert len(merged) == 2
    assert [100, 50, 25] in merged_colors.tolist()


def test_umeyama_recovers_a_similarity():
    rng = np.random.default_rng(4)
    source = rng.normal(size=(30, 3))
    angle = 0.7
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    target = 1.7 * source @ rotation.T + [1, 2, 3]
    scale, found, shift = umeyama(source, target)
    assert scale == pytest.approx(1.7)
    assert np.allclose(found, rotation)
    assert np.allclose(shift, [1, 2, 3])


def test_names_are_compared_against_a_short_list_of_synonyms():
    assert name_matches("armchair", "chair")
    assert name_matches("potted plant", "plant")
    assert not name_matches("cardboard box", "basket")
    assert not name_matches("wooden stool", "chair")


def test_a_floating_box_settles_onto_what_holds_it_up():
    floating = Box(np.array([0.0, 0.0, 0.3]), np.array([0.4, 0.4, 0.32]), 0.0)
    settled = settle(floating, [0.0])
    assert settled.center[2] - settled.size[2] / 2 == pytest.approx(0.0)
    assert settled.center[2] + settled.size[2] / 2 == pytest.approx(0.46)
    on_table = Box(np.array([0.0, 0.0, 0.7]), np.array([0.3, 0.3, 0.2]), 0.0)
    assert settle(on_table, [0.0, 0.45]).center[2] - settle(on_table, [0.0, 0.45]).size[2] / 2 == pytest.approx(0.45)
    on_wall = Box(np.array([0.0, 0.0, 1.6]), np.array([0.5, 0.1, 0.6]), 0.0)
    assert settle(on_wall, [0.0]) is on_wall


def test_overlap_is_one_for_the_same_box_and_a_third_for_half_a_box_off():
    a = {"center": np.array([0.0, 0.0, 0.5]), "size": np.array([1.0, 1.0, 1.0]), "yaw_deg": 0.0}
    b = {**a, "center": np.array([0.5, 0.0, 0.5])}
    far = {**a, "center": np.array([3.0, 0.0, 0.5])}
    assert box_overlap(a, a) == pytest.approx(1.0, abs=0.03)
    assert box_overlap(a, b) == pytest.approx(1 / 3, abs=0.03)
    assert box_overlap(a, far) == 0.0


def test_a_known_phone_height_rescales_the_room():
    views = [camera_at([0, 0, 0], epoch=0) for _ in range(3)]
    for view, height in zip(views, (1.5, 1.6, 1.7)):
        view.cam_to_world[2, 3] = height
    assert height_scale(views, 1.4) == pytest.approx(1.4 / 1.6)
    assert height_scale(views, None) == 1.0
    grown = views[0].scaled(2.0)
    assert grown.position[2] == pytest.approx(3.0)
    assert float(grown.depth[0, 0]) == pytest.approx(6.0)


def test_a_tilted_plane_with_a_small_offset_is_not_taken_for_the_floor():
    from standardphysics_changes.geometry import _height_under

    up = np.array([0.0, 0.0, 1.0])
    centre = np.array([3.0, 0.0, 0.5])
    floor = (np.array([0.0, 0.0, 1.0]), 0.0)
    tilt = np.radians(30)
    slope = (np.array([-np.sin(tilt), 0.0, np.cos(tilt)]), -0.5)
    assert slope[1] < floor[1]
    assert _height_under(centre, *floor, up) < _height_under(centre, *slope, up)
