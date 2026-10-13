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


def test_a_route_onto_or_off_a_surface_reads_naturally():
    onto = language.Route(before="between the console table and the wooden bench", after="on the open floor")
    assert language.moved_sentence("armchair", 1.68, None, onto) == (
        "The armchair moved 1.7 m from between the console table and the wooden bench onto the open floor."
    )
    off = language.Route(before="on the coffee table", after="beside the sofa")
    assert language.moved_sentence("basket", 0.8, None, off) == (
        "The basket moved 80 cm from the coffee table to beside the sofa."
    )


def test_a_thing_seen_once_doubts_the_right_thing():
    assert language.unchecked_sentence("plastic crate", "near the sofa", "after") == (
        "A plastic crate near the sofa shows only in the after video; the before video never looked there, "
        "so it may or may not be new."
    )
    assert language.unchecked_sentence("wooden chair", "", "before").endswith("so it may or may not still be there.")


def test_more_than_one_thing_takes_no_article():
    assert language.added_sentence("white ceramic plates", "on the nightstand") == "White ceramic plates appeared on the nightstand."
    assert language.added_sentence("glass vase", "") == "A glass vase appeared."
    assert language.summary([{"type": "added", "name": "stacked plates"}]) == (
        "One thing changed between the videos: stacked plates appeared."
    )
    assert language.unchecked_sentence("wooden chairs", "", "before") == (
        "Wooden chairs show only in the before video; the after video never looked there, "
        "so they may or may not still be there."
    )


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


def test_a_round_thing_never_claims_a_turn():
    from standardphysics_changes.changes import visible_turn

    assert visible_turn("oil drum", 120.0) is None
    assert visible_turn("armchair", 90.0) == 90.0


def test_a_hanging_box_is_described_as_not_counted():
    sentence = language.unsupported_sentence("dark wooden bed post", "added", 0.78)
    assert sentence.startswith("A dark wooden bed post seems to have appeared 80 cm above the floor")
    assert sentence.endswith("is not counted.")


def test_number_follows_the_noun_the_phrase_is_about():
    assert language.some("green suitcase with photos") == "a green suitcase with photos"
    assert language.is_plural("white ceramic plates")
    assert not language.is_plural("brown wooden seat with black metal legs")


def test_a_half_turn_reads_as_turning_around():
    assert language.turn_phrase(-178.0) == " and turned around"
    assert language.turn_phrase(90.0) == " and turned about 90° counterclockwise"


def test_views_that_disagree_on_the_kind_of_thing_give_no_name():
    from standardphysics_changes.naming import agreed_names, kind_of

    class Scripted:
        def __init__(self, *answers):
            self.answers = list(answers)

        def name(self, *images):
            return {"name": self.answers.pop(0), "detail": "", "where": ""}

    assert kind_of("bookshelf") == kind_of("metal rack")
    assert agreed_names(Scripted("stool", "wooden stool"), [None, None])["name"] == "stool"
    assert agreed_names(Scripted("toy truck", "stool"), [None, None]) is None
    assert language.plain_noun([0.3, 0.2, 0.4]) == "object"
    assert language.plain_noun([0.2, 0.2, 0.1]) == "small object"
