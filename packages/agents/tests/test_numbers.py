"""The display boundary. Inches become words here and nowhere else."""

from __future__ import annotations

from standardphysics_agents.numbers import by, inches, measured, plural, size, things


def test_a_whole_number_stays_whole():
    assert inches(36.0) == "36 inches"


def test_one_inch_is_singular():
    assert inches(1.0) == "1 inch"


def test_a_measured_value_keeps_one_decimal():
    assert inches(43.307) == "43.3 inches"


def test_a_hair_off_a_whole_number_reads_as_the_whole_number():
    assert inches(35.999) == "36 inches"


def test_common_fractions_are_words():
    assert inches(0.5) == "half an inch"
    assert inches(0.25) == "a quarter inch"


def test_a_shortfall_is_never_rounded_into_looking_like_a_pass():
    """35.98 against a 36 inch minimum must not print as "36 inches"."""
    assert measured(35.98, 36.0) == "35.98 inches"


def test_a_measurement_that_really_met_the_threshold_reads_plainly():
    assert measured(36.0, 36.0) == "36 inches"


def test_a_clear_shortfall_needs_no_extra_digits():
    assert measured(31.0, 36.0) == "31 inches"


def test_no_required_value_means_no_comparison_to_hide():
    assert measured(35.98) == "36 inches"


def test_a_size_sits_in_front_of_a_noun():
    assert f"a {size(60.0)} circle" == "a 60 inch circle"


def test_a_rectangle_reads_as_one_measurement():
    assert by(48.0, 30.0) == "48 by 30 inches"


def test_two_of_the_same_thing_are_counted():
    assert things(["Display case", "Display case"]) == "the two display cases"


def test_one_thing_is_named():
    assert things(["Table"]) == "the table"


def test_two_different_things_are_both_named():
    assert things(["Ordering counter", "Table"]) == "the ordering counter and the table"


def test_nothing_to_name_is_nothing():
    assert things([]) is None


def test_plurals_that_need_an_e():
    assert plural("Display case") == "display cases"
    assert plural("Box") == "boxes"
    assert plural("Bench") == "benches"
