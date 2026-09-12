"""The command line a person uses to turn a check on."""

from __future__ import annotations

import pytest
from standardphysics_agents.cli import main
from standardphysics_agents.rules import LEDGER_PATH_ENV, load_ledger, load_pack


@pytest.fixture
def ledger_file(tmp_path, monkeypatch):
    """Nothing in here writes the ledger the package ships with."""
    path = tmp_path / "verification.json"
    monkeypatch.setenv(LEDGER_PATH_ENV, str(path))
    return path


def test_listing_shows_every_rule_and_its_state(capsys, ledger_file):
    assert main(["rules", "list", "--tier", "3"]) == 0
    printed = capsys.readouterr().out
    assert "route_clear_width" in printed
    assert "waiting on a person" in printed


def test_showing_a_rule_prints_the_sentence_behind_it(capsys, ledger_file):
    assert main(["rules", "show", "route_clear_width"]) == 0
    printed = capsys.readouterr().out
    assert "403.5.1" in printed
    assert "36 inches (915 mm) minimum" in printed


def test_the_wrong_number_leaves_the_check_off(capsys, ledger_file):
    code = main(
        ["rules", "verify", "route_clear_width", "--by", "Dana", "--threshold", "30"]
    )
    assert code == 1
    assert not ledger_file.exists()


def test_reading_the_number_back_turns_the_check_on(capsys, ledger_file):
    code = main(
        ["rules", "verify", "route_clear_width", "--by", "Dana", "--threshold", "36"]
    )
    assert code == 0
    rule = load_pack().by_id("route_clear_width")
    assert load_ledger().entry_for(rule).verified_by == "Dana"


def test_a_second_reader_is_recorded(ledger_file):
    main(["rules", "verify", "door_clear_width", "--by", "Dana", "--threshold", "32"])
    assert main(["rules", "second-check", "door_clear_width", "--by", "Sam"]) == 0
    assert load_ledger().double_checked(load_pack().by_id("door_clear_width"))


def test_running_the_checks_with_nothing_verified_says_so(capsys, ledger_file):
    assert main(["check", "--provider", "stub"]) == 0
    assert "No checks are enabled" in capsys.readouterr().out


def test_running_the_checks_reports_the_pinch(capsys, ledger_file):
    main(["rules", "verify", "route_clear_width", "--by", "Dana", "--threshold", "36"])
    capsys.readouterr()
    assert main(["check", "--provider", "stub"]) == 0
    printed = capsys.readouterr().out
    assert "The path to the counter is too narrow" in printed
    assert "31 inches at the tightest point" in printed
