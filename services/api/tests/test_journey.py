"""Where each shop is in the owner's journey, and the checklist behind it."""

from conftest import create_scan, drain


def _sample(make_client):
    client = make_client(seed=True).__enter__()
    drain(client)
    return client, client.get("/api/scans").json()["scans"][0]["id"]


def _journey(client, scan_id):
    return client.get(f"/api/scans/{scan_id}/journey").json()


def _answer_everything(client, scan_id):
    for request in client.get(f"/api/scans/{scan_id}/requests").json()["requests"]:
        if request["timing"] == "in_shop":
            client.post(f"/api/scans/{scan_id}/requests/{request['id']}/skip")


def test_a_walk_still_uploading_is_in_the_walk_stage(client):
    scan_id = create_scan(client)
    journey = _journey(client, scan_id)
    assert journey["stage"] == "walk"
    assert journey["next_step"] == {"kind": "upload", "title": "Finish uploading your walk", "count": None}
    assert journey["tools_unlocked"] is False


def test_the_quick_questions_come_first(make_client):
    client, scan_id = _sample(make_client)
    journey = _journey(client, scan_id)
    assert journey["stage"] == "fill_in_the_gaps"
    assert journey["next_step"]["title"] == "Answer 2 quick questions"
    client.put(f"/api/scans/{scan_id}/requests/restroom/answer", json={"yes": False})
    client.put(f"/api/scans/{scan_id}/requests/inside_doors/answer", json={"yes": False})
    assert _journey(client, scan_id)["next_step"]["title"] == "Take 3 more photos"


def test_the_results_are_ready_once_the_gaps_are_filled(make_client):
    client, scan_id = _sample(make_client)
    _answer_everything(client, scan_id)
    for request in client.get(f"/api/scans/{scan_id}/requests").json()["requests"]:
        if request["timing"] == "follow_up" and request["kind"] == "number":
            client.put(f"/api/scans/{scan_id}/requests/{request['id']}/answer", json={"number": 34})
    journey = _journey(client, scan_id)
    assert journey["stage"] == "results"
    assert journey["next_step"]["title"].startswith("Your results are ready.")
    assert journey["tools_unlocked"] is True


def test_the_checklist_counts_what_the_owner_has_dealt_with(make_client):
    client, scan_id = _sample(make_client)
    checklist = client.get(f"/api/scans/{scan_id}/checklist").json()
    assert checklist["done"] == 0
    assert checklist["total"] == len(checklist["items"]) > 1
    first = checklist["items"][0]["finding_id"]
    marked = client.put(f"/api/scans/{scan_id}/checklist/{first}", json={"status": "needs_pro"})
    assert marked.json()["status"] == "needs_pro"
    assert client.get(f"/api/scans/{scan_id}/checklist").json()["done"] == 1


def test_marking_something_that_is_not_a_problem_is_refused(make_client):
    client, scan_id = _sample(make_client)
    passing = next(f for f in client.get(f"/api/scans/{scan_id}/assessment").json()["findings"] if f["outcome"] == "passes")
    assert client.put(f"/api/scans/{scan_id}/checklist/{passing['id']}", json={"status": "done"}).status_code == 404


def test_fixing_says_how_far_along_and_what_is_next(make_client):
    client, scan_id = _sample(make_client)
    _answer_everything(client, scan_id)
    for request in client.get(f"/api/scans/{scan_id}/requests").json()["requests"]:
        if request["timing"] == "follow_up" and request["kind"] == "number":
            client.put(f"/api/scans/{scan_id}/requests/{request['id']}/answer", json={"number": 34})
    items = client.get(f"/api/scans/{scan_id}/checklist").json()["items"]
    client.put(f"/api/scans/{scan_id}/checklist/{items[0]['finding_id']}", json={"status": "done"})
    journey = _journey(client, scan_id)
    assert journey["stage"] == "fix"
    assert journey["next_step"]["title"].startswith(f"1 of {len(items)} done. Next: ")
    for item in items:
        client.put(f"/api/scans/{scan_id}/checklist/{item['finding_id']}", json={"status": "not_doing"})
    assert _journey(client, scan_id)["next_step"] == {"kind": "done", "title": "Everything on your list is done", "count": None}


def test_the_home_card_lists_every_shop_on_the_account(client, stranger):
    create_scan(client)
    create_scan(client)
    assert len(client.get("/api/journeys").json()["journeys"]) == 2
    assert stranger.get("/api/journeys").json()["journeys"] == []


def test_the_journey_list_needs_a_sign_in(make_client):
    with make_client(sign_in_as_owner=False) as anonymous:
        assert anonymous.get("/api/journeys").status_code == 401
