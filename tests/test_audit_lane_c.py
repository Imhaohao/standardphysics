"""Regressions for audit findings in Lane C's checks.

Each test is a case that returned the wrong answer, or crashed, before its fix.
"""

from standardphysics_agents import assess, load_pack
from standardphysics_agents.checks.turn_width import turn_verdict
from standardphysics_api.stages import preview_ledger
from standardphysics_fixtures import build_graph, build_scenario
from standardphysics_pipeline.measure import PipelineMeasurements

TURN_RULE = load_pack().by_id("turn_clear_width")


def test_a32_an_unmeasured_zone_does_not_pass_the_turn():
    verdict = turn_verdict(12.0, None, 48.0, 42.0, TURN_RULE)
    assert (verdict.applies, verdict.satisfied) == (False, False)


def test_a32_a_measured_zone_that_is_too_tight_still_fails_the_turn():
    verdict = turn_verdict(12.0, None, 40.0, 42.0, TURN_RULE)
    assert (verdict.applies, verdict.satisfied, verdict.reason) == (True, False, "at_turn_too_tight")


def test_a32_the_fixture_shop_assesses_with_an_unmeasured_turn_zone():
    result = assess(
        build_graph(), build_scenario(), PipelineMeasurements(), ledger=preview_ledger(), pass_number=1
    )
    assert all(finding.measured_inches != 0.0 for finding in result.assessment.findings)
