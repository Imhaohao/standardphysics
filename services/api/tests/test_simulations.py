from __future__ import annotations

import json
import pytest
from standardphysics_contracts import SimulationRequest, graph_hash
from standardphysics_api import repository as repo
from standardphysics_api.simulations import SIMULATE
from standardphysics_api.stages import Stages
from standardphysics_agents.router import Rejected
from conftest import drain, no_blender_stages


def shop(client):
    return client.get('/api/scans').json()['scans'][0]['id']


def test_screening_is_queued_snapshotted_and_does_not_save_a_layout(make_client):
    with make_client(seed=True) as client:
        scan_id = shop(client)
        before = client.get(f'/api/scans/{scan_id}/scene').json()
        response = client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 0, 'samples': 4, 'max_workers': 2})
        assert response.status_code == 202, response.text
        assert response.json()['state'] == 'queued'
        assert client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 0}).status_code == 409
        drain(client)
        result = client.get(f'/api/scans/{scan_id}/simulations?revision=0').json()
        assert result['state'] == 'done', result
        assert result['completed'] == 4
        assert result['result']['total_runs'] == 4
        assert result['result']['feedback']
        assert result['result']['unique_layouts'] >= 1
        assert result['result']['preview'] is True
        assert result['result']['limitations']
        assert client.get(f'/api/scans/{scan_id}/scene').json() == before


def test_live_preflight_rejects_missing_key_before_queuing(make_client, monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    with make_client(seed=True) as client:
        scan_id = shop(client)
        response = client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 0, 'router': 'typesafe'})
        assert response.status_code == 409
        assert client.get(f'/api/scans/{scan_id}/simulations?revision=0').status_code == 404


def test_job_limits_and_stale_layout_rejected(make_client):
    with make_client(seed=True) as client:
        scan_id = shop(client)
        for body in ({'samples': 10001}, {'samples': 0}, {'max_workers': 17}, {'max_workers': 0}, {'router': 'made-up'}, {'unknown': True}):
            response = client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 0, **body})
            assert response.status_code == 400
        response = client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 9})
        assert response.status_code == 409


def test_simulation_failure_keeps_room_ready_and_sanitizes_errors(make_client, monkeypatch):
    def fail(*args):
        raise RuntimeError('secret upstream payload')
    monkeypatch.setattr('standardphysics_api.worker.run_simulation', fail)
    with make_client(seed=True) as client:
        scan_id = shop(client)
        client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 0, 'samples': 1})
        drain(client)
        state = client.get(f'/api/scans/{scan_id}/simulations?revision=0').json()
        assert state['state'] == 'failed'
        assert 'secret upstream payload' not in state['error']
        assert client.get(f'/api/scans/{scan_id}').json()['state'] == 'ready'


def test_rebuild_keeps_measured_geometry_and_rejects_stale_revision(make_client):
    calls = []

    def label(graph):
        calls.append(graph.revision)
        return graph.model_copy(update={'nodes': [node.model_copy(update={'label': 'Reviewed ' + node.label}) for node in graph.nodes]})
    with make_client(seed=True, stages=no_blender_stages(label=label)) as client:
        scan_id = shop(client)
        before = client.get(f'/api/scans/{scan_id}/scene').json()
        result = client.post(f'/api/scans/{scan_id}/rebuild', json={'base_revision': 0})
        assert result.status_code == 201, result.text
        assert calls == [0]
        after = result.json()
        assert after['revision'] == 1
        for original, rebuilt in zip(before['nodes'], after['nodes']):
            assert original['dimensions'] == rebuilt['dimensions']
            assert original['transform'] == rebuilt['transform']
            assert original['id'] == rebuilt['id']
            assert rebuilt['label'].startswith('Reviewed ')
        assert client.post(f'/api/scans/{scan_id}/rebuild', json={'base_revision': 0}).status_code == 409
        drain(client)
        with client.app.state.database.connect() as connection:
            assert repo.get_revision(connection, __import__('uuid').UUID(scan_id), 1)['glb_path'] is not None


def test_deleting_room_cleans_queued_simulation(make_client):
    with make_client(seed=True) as client:
        scan_id = shop(client)
        assert client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 0, 'samples': 1}).status_code == 202
        assert client.delete(f'/api/scans/{scan_id}').status_code == 204
        assert client.get(f'/api/scans/{scan_id}/simulations?revision=0').status_code == 404
        drain(client)


def test_deletion_waits_for_running_jobs(make_client):
    with make_client(seed=True) as client:
        scan_id = shop(client)
        client.post(f'/api/scans/{scan_id}/simulations', json={'base_revision': 0, 'samples': 1})
        with client.app.state.database.transaction() as connection:
            connection.execute("UPDATE jobs SET state='running' WHERE scan_id=? AND kind='simulate'", (scan_id,))
        assert client.delete(f'/api/scans/{scan_id}').status_code == 409
        assert client.get(f'/api/scans/{scan_id}').status_code == 200
