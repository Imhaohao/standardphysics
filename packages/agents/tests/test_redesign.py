from uuid import uuid4

from standardphysics_agents.models import ModelAnswer
from standardphysics_agents.redesign import validate_redesign, propose_redesign
from standardphysics_agents.router import Rejected
from standardphysics_agents.workflows import Workflow, WHEELCHAIR_PROFILE
from standardphysics_agents.rules import VerificationLedger
from standardphysics_fixtures import node_id


def answer(moves):
    return ModelAnswer({'moves': moves}, 'OpenAI', 'openai/gpt-6-astra')


def move(node, dx=0, dy=0):
    return {'node_id': str(node), 'dx': dx, 'dy': dy, 'rotation_degrees': 0}


def validate(graph, scenario, pipeline, pack, ledger, moves):
    return validate_redesign(graph, answer(moves), [Workflow(id='room', title='Room', scenario=scenario)], [WHEELCHAIR_PROFILE], pipeline, rules=pack, ledger=ledger)


def test_model_cannot_move_a_fixed_fixture(graph, scenario, pipeline, pack, ledger):
    result = validate(graph, scenario, pipeline, pack, ledger, [move(node_id('counter'), dx=1)])
    assert not result.accepted
    assert 'moved_something_fixed' in result.reasons
    assert result.graph is None


def test_model_cannot_resize_inject_unknown_ids_or_nonfinite_moves(graph, scenario, pipeline, pack, ledger):
    for moves in ([{**move(node_id('table_1')), 'dimensions': [0,0,0]}], [move(uuid4())], [move(node_id('table_1'), dx=float('nan'))], [move(node_id('table_1'))]*2):
        result = validate(graph, scenario, pipeline, pack, ledger, moves)
        assert not result.accepted
        assert result.graph is None


def test_model_cannot_get_two_moved_objects_to_overlap(graph, scenario, pipeline, pack, ledger):
    a, b = graph.by_id(node_id('table_1')), graph.by_id(node_id('table_2'))
    result = validate(graph, scenario, pipeline, pack, ledger, [
        move(a.id, dx=-a.transform.position.x, dy=-a.transform.position.y),
        move(b.id, dx=-b.transform.position.x, dy=-b.transform.position.y),
    ])
    assert not result.accepted
    assert 'collided' in result.reasons


def test_model_edits_need_verified_rules(graph, scenario, pipeline, pack):
    result = validate(graph, scenario, pipeline, pack, VerificationLedger(), [move(node_id('table_1'))])
    assert not result.accepted
    assert 'no_verified_rules' in result.reasons


def test_unavailable_openrouter_is_reported_without_inventing_a_redesign(graph, scenario, pipeline, pack, ledger):
    class Unavailable:
        model = 'requested-astra'
        def structured(self, *args):
            return Rejected('openrouter_not_configured')
    result = propose_redesign(graph, [], [], [], pipeline, rules=pack, ledger=ledger, model=Unavailable())
    assert not result.accepted
    assert result.reasons == ('openrouter_not_configured',)
    assert result.graph is None


def test_validated_aisle_improvement_preserves_all_objects_and_dimensions(graph, scenario, pipeline, pack, ledger):
    from standardphysics_contracts import to_meters
    result = validate(graph, scenario, pipeline, pack, ledger, [move(node_id('case_east'), dx=to_meters(5))])
    assert result.accepted, result.reasons
    assert result.graph is not None
    assert {node.id: node.dimensions for node in result.graph.nodes} == {node.id: node.dimensions for node in graph.nodes}
    assert result.graph.by_id(node_id('counter')) == graph.by_id(node_id('counter'))
