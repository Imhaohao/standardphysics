"""An owner renames a shop, and every list of their shops shows the new name."""

import pytest

from conftest import create_scan, unknown_scan


def _rename(client, scan_id: str, name: str):
    return client.patch(f"/api/scans/{scan_id}", json={"name": name})


def _name_of(client, scan_id: str) -> str:
    return client.get(f"/api/scans/{scan_id}").json()["name"]


def _walk_again(client, shop: str) -> str:
    """A walk that joins the shop, the way adding a room does."""
    response = client.post(
        "/api/scans",
        json={"name": "Corner cafe", "device_model": "iPhone17,1", "duration_seconds": 90.0, "replaces": shop},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_an_owner_renames_their_shop_and_every_list_shows_it(client):
    scan_id = create_scan(client)

    renamed = _rename(client, scan_id, "  Tea House Annex  ")

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Tea House Annex"
    assert _name_of(client, scan_id) == "Tea House Annex"
    assert [scan["name"] for scan in client.get("/api/scans").json()["scans"]] == ["Tea House Annex"]
    assert client.get(f"/api/scans/{scan_id}/journey").json()["shop_name"] == "Tea House Annex"
    assert [journey["shop_name"] for journey in client.get("/api/journeys").json()["journeys"]] == ["Tea House Annex"]


def test_another_owner_cannot_rename_a_shop_that_is_not_theirs(client, stranger):
    scan_id = create_scan(client)

    response = _rename(stranger, scan_id, "Mine now")

    assert response.status_code == 404
    assert response.json() == {"error": "no scan"}
    assert _name_of(client, scan_id) == "Corner cafe"


def test_renaming_a_shop_that_does_not_exist_is_not_found(client):
    assert _rename(client, unknown_scan(), "Tea House").status_code == 404


@pytest.mark.parametrize("name", ["", "   ", "x" * 121], ids=["empty", "only spaces", "too long"])
def test_a_name_that_is_empty_or_too_long_is_refused(client, name):
    scan_id = create_scan(client)

    response = _rename(client, scan_id, name)

    assert response.status_code == 400
    assert response.json() == {"error": "invalid request", "need": ["body.name"]}
    assert _name_of(client, scan_id) == "Corner cafe"


def test_the_longest_name_a_shop_may_have_is_kept_whole(client):
    scan_id = create_scan(client)
    assert _rename(client, scan_id, "x" * 120).json()["name"] == "x" * 120


def test_a_walk_still_being_measured_for_the_shop_keeps_the_new_name(client):
    """Once measured, the new walk replaces the old scan in the list, and the name has to survive that."""
    shop = create_scan(client)
    rewalk = _walk_again(client, shop)

    _rename(client, shop, "Tea House Annex")
    assert _name_of(client, rewalk) == "Tea House Annex"

    _rename(client, rewalk, "Tea House")
    assert _name_of(client, shop) == "Tea House"


def test_renaming_one_shop_leaves_the_others_alone(client):
    renamed, other = create_scan(client), create_scan(client)

    _rename(client, renamed, "Tea House")

    assert _name_of(client, other) == "Corner cafe"
