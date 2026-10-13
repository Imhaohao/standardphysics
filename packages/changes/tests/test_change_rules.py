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
from standardphysics_changes.pipeline import Scene, distinguish, empty_share, objects_only, regions_of
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
    far = rng.uniform([8.8, 8.8, 0.0], [9.2, 9.2, 0.4], (100, 3))
    points = np.vstack([seat, legs, new, far])
    old = Region("removed", 0, np.arange(200), fit_box(seat), 200, names={"name": "plastic chair"})
    stray = Region("removed", 0, np.arange(200, 300), fit_box(legs), 100, names={"name": "white plastic chair"})
    box = Region("removed", 0, np.arange(500, 600), fit_box(far), 100, names={"name": "cardboard box"})
    after = Region("added", 1, np.arange(300, 500), fit_box(new), 200, names={"name": "plastic chair"})
    move = Move(old, after, 3.0, None, 1.0)
    loose_removed, loose_added = absorb_fragments([move], [stray, box], [], points)
    assert loose_removed == [box] and loose_added == []
    assert len(move.removed.point_ids) == 300


def test_the_vision_model_can_refile_a_piece_of_the_right_size():
    from standardphysics_changes.landmarks import settle_kind

    def piece(category, size):
        return Landmark(np.arange(2000), Box(np.array([0.0, 0.0, 0.4]), np.array(size), 0.0), category)

    assert settle_kind(piece("chair", [0.5, 0.5, 0.9]), "wooden chair")
    assert settle_kind(piece("table", [1.0, 0.5, 0.8]), "object")
    nightstand = piece("chair", [0.5, 0.4, 0.6])
    assert settle_kind(nightstand, "nightstand") and nightstand.category == "cabinet"
    bench = piece("table", [1.2, 0.45, 0.9])
    assert settle_kind(bench, "wooden bench") and bench.category == "bench"
    assert not settle_kind(piece("shelf", [1.0, 0.4, 1.8]), "staircase")
    assert not settle_kind(piece("table", [0.3, 0.3, 0.3]), "sofa")


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


def test_a_box_hanging_over_empty_space_has_little_support():
    from standardphysics_changes.regions import support_share

    rng = np.random.default_rng(3)
    table_top = np.column_stack([rng.uniform(-0.5, 0.5, 4000), rng.uniform(-0.5, 0.5, 4000), np.full(4000, 0.75)])
    on_table = Box(np.array([0.0, 0.0, 0.85]), np.array([0.3, 0.3, 0.2]), 0.0)
    over_edge = Box(np.array([0.5, 0.0, 0.85]), np.array([0.4, 0.3, 0.2]), 0.0)
    on_floor = Box(np.array([3.0, 0.0, 0.2]), np.array([0.3, 0.3, 0.4]), 0.0)
    assert support_share(on_table, table_top) > 0.9
    assert support_share(over_edge, table_top) < 0.6
    assert support_share(on_floor, table_top) == 1.0


def test_the_namer_gets_a_second_view_only_when_it_shows_enough():
    from types import SimpleNamespace

    from standardphysics_changes.pipeline import clearest_two

    views = [SimpleNamespace(visible=1.0), SimpleNamespace(visible=0.6), SimpleNamespace(visible=0.5)]
    assert len(clearest_two(views)) == 2
    assert len(clearest_two([views[0], SimpleNamespace(visible=0.3)])) == 1


def test_a_table_top_is_its_densest_layer_not_its_highest_points():
    from standardphysics_changes.landmarks import supports_under

    rng = np.random.default_rng(9)
    top = np.column_stack([rng.uniform(0, 0.6, 3000), rng.uniform(0, 0.5, 3000), rng.uniform(0.69, 0.70, 3000)])
    smeared = np.column_stack([rng.uniform(0.2, 0.4, 600), rng.uniform(0.15, 0.35, 600), rng.uniform(0.70, 0.80, 600)])
    front = np.column_stack([rng.uniform(0, 0.6, 1500), np.zeros(1500), rng.uniform(0.0, 0.7, 1500)])
    points = np.vstack([top, smeared, front])
    table = Landmark(np.arange(len(points)), fit_box(points), "cabinet", "side table")
    basket = Box(np.array([0.3, 0.25, 0.82]), np.array([0.2, 0.2, 0.06]), 0.0)
    assert supports_under(basket, [table], points)[0] == pytest.approx(0.70, abs=0.02)


def test_a_desk_fused_with_the_bench_beside_it_comes_apart():
    from standardphysics_changes.landmarks import find_landmarks

    rng = np.random.default_rng(5)
    desk = rng.uniform([0.0, 0.0, 0.72], [2.0, 0.9, 0.75], (40000, 3))
    bench = rng.uniform([2.06, 0.0, 0.72], [3.2, 0.5, 0.75], (15000, 3))
    points = np.vstack([desk, bench])
    found = find_landmarks(points, np.zeros(len(points), np.uint8), np.zeros(len(points), int), {0: "table-merged"}, 2.5)
    assert sorted(round(float(piece.box.size[:2].max()), 1) for piece in found) == [1.1, 2.0]


def test_a_chair_base_under_its_seat_joins_the_move_whatever_it_is_called():
    from standardphysics_changes.matching import Move, absorb_fragments

    rng = np.random.default_rng(11)
    seat = rng.uniform([0.0, 0.0, 0.35], [0.8, 0.8, 0.9], (400, 3))
    base = rng.uniform([0.2, 0.2, 0.0], [0.6, 0.6, 0.3], (120, 3))
    beside = rng.uniform([1.0, 0.0, 0.0], [1.3, 0.3, 0.3], (120, 3))
    old = rng.uniform([4.0, 0.0, 0.0], [4.8, 0.8, 0.9], (400, 3))
    points = np.vstack([seat, base, beside, old])
    chair = Region("added", 1, np.arange(400), fit_box(seat), 400, names={"name": "leather chair"})
    star = Region("added", 1, np.arange(400, 520), fit_box(base), 120, names={"name": "metallic chair base"})
    basket = Region("added", 1, np.arange(520, 640), fit_box(beside), 120, names={"name": "basket"})
    gone = Region("removed", 0, np.arange(640, 1040), fit_box(old), 400, names={"name": "leather chair"})
    move = Move(gone, chair, 4.0, None, 1.0)
    _, loose_added = absorb_fragments([move], [], [star, basket], points)
    assert loose_added == [basket]
    assert move.added.box.center[2] - move.added.box.size[2] / 2 < 0.05


def test_a_box_must_fit_the_kind_of_thing_it_is_called():
    from standardphysics_changes.landmarks import fits_kind

    def box(x, y):
        return Box(np.array([0.0, 0.0, 0.5]), np.array([x, y, 0.9]), 0.0)

    assert fits_kind(box(0.6, 0.55), "wooden chair")
    assert not fits_kind(box(1.32, 0.9), "wooden chair")
    assert not fits_kind(box(0.37, 1.24), "dark wooden chair")
    assert fits_kind(box(1.3, 0.9), "toy truck")


def test_a_chair_grown_into_the_bin_beside_it_is_cut_apart():
    from standardphysics_changes.evidence import GONE
    from standardphysics_changes.pipeline import _finer_pieces

    rng = np.random.default_rng(13)
    chair = rng.uniform([0.0, 0.0, 0.05], [0.6, 0.6, 0.9], (30000, 3))
    bin_ = rng.uniform([0.65, 0.0, 0.05], [1.2, 0.55, 0.9], (30000, 3))
    lid = rng.uniform([1.25, 0.1, 0.05], [1.37, 0.45, 0.5], (4000, 3))
    points = np.vstack([chair, bin_, lid])
    status = np.full(len(points), GONE, np.uint8)
    scene = scene_with(points, status, np.zeros(len(points)), np.zeros(len(points)), 1)
    merged = Region("added", 1, np.arange(len(points)), fit_box(points), len(points))
    pieces = _finer_pieces(scene, merged, RegionRules())
    assert sorted(len(piece.point_ids) for piece in pieces) == [30000, 34000]


def test_without_appearance_fingerprints_a_move_still_pairs_on_the_same_specific_name():
    from standardphysics_changes.matching import pair_moves

    rng = np.random.default_rng(17)
    old = rng.uniform([0.0, 0.0, 0.0], [0.5, 0.5, 0.8], (200, 3))
    new = rng.uniform([3.0, 0.0, 0.0], [3.5, 0.5, 0.8], (200, 3))
    plain_old = rng.uniform([6.0, 0.0, 0.0], [6.4, 0.4, 0.4], (100, 3))
    plain_new = rng.uniform([9.0, 0.0, 0.0], [9.4, 0.4, 0.4], (100, 3))
    points = np.vstack([old, new, plain_old, plain_new])
    gone = Region("removed", 0, np.arange(200), fit_box(old), 200, names={"name": "plastic chair"})
    came = Region("added", 1, np.arange(200, 400), fit_box(new), 200, names={"name": "plastic chair"})
    vague_gone = Region("removed", 0, np.arange(400, 500), fit_box(plain_old), 100, names={"name": "object"})
    vague_came = Region("added", 1, np.arange(500, 600), fit_box(plain_new), 100, names={"name": "object"})
    moves = pair_moves([gone, vague_gone], [came, vague_came], points)
    assert [(move.removed, move.added) for move in moves] == [(gone, came)]


def test_something_set_on_top_of_a_moved_table_is_not_folded_into_the_move():
    from standardphysics_changes.matching import Move, absorb_fragments

    rng = np.random.default_rng(19)
    table = rng.uniform([0.0, 0.0, 0.0], [1.2, 0.8, 0.75], (600, 3))
    lamp = rng.uniform([0.4, 0.3, 0.76], [0.6, 0.5, 1.2], (150, 3))
    old = rng.uniform([4.0, 0.0, 0.0], [5.2, 0.8, 0.75], (600, 3))
    points = np.vstack([table, lamp, old])
    moved_to = Region("added", 1, np.arange(600), fit_box(table), 600, names={"name": "wooden table"})
    set_down = Region("added", 1, np.arange(600, 750), fit_box(lamp), 150, names={"name": "desk lamp"})
    moved_from = Region("removed", 0, np.arange(750, 1350), fit_box(old), 600, names={"name": "wooden table"})
    move = Move(moved_from, moved_to, 4.0, None, 1.0)
    _, loose_added = absorb_fragments([move], [], [set_down], points)
    assert loose_added == [set_down]
    assert len(move.added.point_ids) == 600
