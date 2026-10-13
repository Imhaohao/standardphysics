"""Sentences come from the measured numbers, so they are checked against them."""

import numpy as np
from standardphysics_changes import language
from standardphysics_changes.naming import FALLBACK, parse_names


def test_moved_sentence_carries_distance_route_and_turn():
    route = language.Route(before="beside the bookshelf", after="near the window")
    sentence = language.moved_sentence("armchair", 2.66, -152, route)
    assert sentence == "The armchair moved 2.7 m from beside the bookshelf to near the window and turned about 150° clockwise."


def test_a_move_past_furniture_lands_on_its_other_side():
    route = language.Route(before="beside the bookshelf", after="near the cabinet", crossed="coffee table")
    assert language.moved_sentence("armchair", 3.0, None, route) == (
        "The armchair moved 3.0 m from beside the bookshelf to the other side of the coffee table."
    )


def test_a_move_between_two_spots_described_alike_says_where_it_headed():
    route = language.Route(before="on the open floor", after="on the open floor", heading="bookshelf")
    assert language.moved_sentence("stool", 3.2, None, route) == "The stool moved 3.2 m toward the bookshelf."


def test_small_turns_and_distances_read_naturally():
    assert language.moved_sentence("stool", 0.43, 8) == "The stool moved 45 cm."
    assert language.moved_sentence("stool", 0.43, None) == "The stool moved 45 cm."


def test_added_sentence_and_size_read_naturally():
    assert language.added_sentence("old armchair", "on the open floor") == "An old armchair appeared on the open floor."
    assert language.size_phrase(np.array([0.39, 0.52, 0.34])) == "about 50 cm by 40 cm and 35 cm tall"
    assert language.size_phrase(np.array([0.99, 0.91, 0.93])) == "about 1.0 m by 90 cm and 95 cm tall"


def test_summary_lists_every_change():
    changes = [
        {"type": "moved", "name": "armchair", "distance_m": 2.7},
        {"type": "added", "name": "box"},
        {"type": "removed", "name": "potted plant"},
    ]
    assert language.summary(changes) == (
        "3 things changed between the videos: the armchair moved 2.7 m, a box appeared and the potted plant was removed."
    )
    assert language.summary([]).startswith("Nothing in the room")


def test_model_replies_are_parsed_or_fall_back():
    reply = 'Sure: {"name": "Armchair", "detail": "white armchair", "where": "beside the sofa."}'
    assert parse_names(reply) == {"name": "armchair", "detail": "white armchair", "where": "beside the sofa"}
    assert parse_names("no json here") == FALLBACK
    assert parse_names('{"name": "lamp"}')["detail"] == "lamp"
