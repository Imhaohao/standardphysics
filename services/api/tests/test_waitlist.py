import csv
import io
import json


def test_signup_collects_invite_address_without_an_account(make_client):
    with make_client(sign_in_as_owner=False, waitlist_admin_token="a-secret-token") as client:
        assert client.post("/api/waitlist", json={"email": " Student@Example.com ", "role": "student"}).status_code == 202
        assert client.post("/api/waitlist", json={"email": "student@example.com", "role": "shop_owner"}).status_code == 202
        response = client.get("/api/waitlist.csv", headers={"Authorization": "Bearer a-secret-token"})

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["email"] == "student@example.com"
    assert rows[0]["role"] == "shop_owner"
    assert rows[0]["joined_at"]
    assert response.headers["cache-control"] == "no-store"


def test_signup_rejects_invalid_email_and_role(make_client):
    with make_client(sign_in_as_owner=False) as client:
        assert client.post("/api/waitlist", json={"email": "not-an-email", "role": "student"}).status_code == 400
        assert client.post("/api/waitlist", json={"email": "x@example.com", "role": "admin"}).status_code == 400


def test_only_admin_token_can_read_invite_addresses(make_client):
    with make_client(sign_in_as_owner=False, waitlist_admin_token="a-secret-token") as client:
        assert client.post("/api/waitlist", json={"email": "x@example.com", "role": "student"}).status_code == 202
        assert client.get("/api/waitlist.csv").status_code == 401
        assert client.get("/api/waitlist.csv", headers={"Authorization": "Bearer wrong"}).status_code == 401

    with make_client(sign_in_as_owner=False) as client:
        assert client.get("/api/waitlist.csv").status_code == 404


NTFY = "https://ntfy.sh/standardphysics-team-test"


def _alerts(monkeypatch, failure: Exception | None = None):
    sent = []

    class _Delivered:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        sent.append(request)
        if failure is not None:
            raise failure
        return _Delivered()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    return sent


def test_a_new_signup_tells_the_team_who_joined_but_not_their_address(make_client, monkeypatch):
    sent = _alerts(monkeypatch)
    with make_client(sign_in_as_owner=False, team_alert_webhook=NTFY) as client:
        assert client.post("/api/waitlist", json={"email": "owner@example.com", "role": "shop_owner"}).status_code == 202
    assert [request.full_url for request in sent] == [NTFY]
    assert sent[0].get_header("Title") == "New TestFlight waitlist signup"
    assert sent[0].data.decode() == "A shop owner joined the TestFlight waitlist. 1 person is on it now."


def test_joining_again_tells_the_team_nothing_new(make_client, monkeypatch):
    sent = _alerts(monkeypatch)
    with make_client(sign_in_as_owner=False, team_alert_webhook=NTFY) as client:
        client.post("/api/waitlist", json={"email": "owner@example.com", "role": "shop_owner"})
        client.post("/api/waitlist", json={"email": "Owner@Example.com", "role": "student"})
        client.post("/api/waitlist", json={"email": "student@example.com", "role": "student"})
    assert [request.data.decode() for request in sent] == [
        "A shop owner joined the TestFlight waitlist. 1 person is on it now.",
        "A student joined the TestFlight waitlist. 2 people are on it now.",
    ]


def test_a_chat_webhook_gets_the_alert_as_json(make_client, monkeypatch):
    sent = _alerts(monkeypatch)
    hook = "https://hooks.slack.com/services/T000/B000/test"
    with make_client(sign_in_as_owner=False, team_alert_webhook=hook) as client:
        client.post("/api/waitlist", json={"email": "student@example.com", "role": "student"})
    assert sent[0].get_header("Content-type") == "application/json"
    assert json.loads(sent[0].data) == {
        "text": "New TestFlight waitlist signup\nA student joined the TestFlight waitlist. 1 person is on it now."
    }


def test_no_webhook_means_no_alert(make_client, monkeypatch):
    sent = _alerts(monkeypatch)
    with make_client(sign_in_as_owner=False) as client:
        assert client.post("/api/waitlist", json={"email": "student@example.com", "role": "student"}).status_code == 202
    assert sent == []


def test_an_alert_that_cannot_be_delivered_still_keeps_the_signup(make_client, monkeypatch, caplog):
    _alerts(monkeypatch, failure=OSError("ntfy is down"))
    with make_client(sign_in_as_owner=False, team_alert_webhook=NTFY, waitlist_admin_token="a-secret-token") as client:
        assert client.post("/api/waitlist", json={"email": "student@example.com", "role": "student"}).status_code == 202
        listed = client.get("/api/waitlist.csv", headers={"Authorization": "Bearer a-secret-token"}).text
    assert "student@example.com" in listed
    assert "was not delivered" in caplog.text
