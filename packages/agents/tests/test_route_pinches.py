"""The gaps a clearance map marks are the gaps the route width findings name, kept and dropped the same way."""

from standardphysics_agents import CheckContext, VerificationLedger, run_checks
from standardphysics_agents.checks import route_pinches
from standardphysics_agents.checks.route_width import RULE_ID
from standardphysics_contracts import StaffArea, Vec3
from standardphysics_fixtures import node_id

CASES = {node_id("case_west"), node_id("case_east")}


def _context(graph, scenario, pipeline, pack, ledger):
    return CheckContext(graph=graph, scenario=scenario, measure=pipeline, rules=pack, ledger=ledger)


def test_the_pinches_are_the_route_width_observations_the_full_run_keeps(graph, scenario, pipeline, pack, ledger):
    context = _context(graph, scenario, pipeline, pack, ledger)
    kept = [observation for observation in run_checks(context).observations if observation.rule_id == RULE_ID]
    assert route_pinches(context) == kept


def test_two_legs_through_the_gap_between_the_cases_make_one_pinch(graph, scenario, pipeline, pack, ledger):
    pinches = route_pinches(_context(graph, scenario, pipeline, pack, ledger))
    between_the_cases = [pinch for pinch in pinches if set(pinch.relied_on) == CASES]
    assert len(between_the_cases) == 1
    assert len(pinches) < len(scenario.stops) - 1


def test_nothing_is_marked_until_a_person_verifies_the_route_width_rule(graph, scenario, pipeline, pack):
    assert route_pinches(_context(graph, scenario, pipeline, pack, VerificationLedger())) == []


def test_a_gap_inside_a_staff_only_area_is_not_marked(graph, scenario, pipeline, pack, ledger):
    over_the_cases = StaffArea(centre=Vec3(x=0.0, y=0.0, z=0.0), width=2.0, depth=1.0)
    staffed = scenario.model_copy(update={"staff_only": [over_the_cases]})
    pinches = route_pinches(_context(graph, staffed, pipeline, pack, ledger))
    assert not any(set(pinch.relied_on) == CASES for pinch in pinches)
