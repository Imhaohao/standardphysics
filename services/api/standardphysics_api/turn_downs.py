"""Pieces the owner turned down where a suggestion put them.

Each turned-down piece becomes a stated `not_there` wish on the scan, so every
later proposal and Fix room loop is refused a layout that puts it back in that
spot (it may still go somewhere else). The whole suggestion is also appended
to the training records, with what was turned down, as preference data for a
later fine-tune: this is the feedback signal, and the wish is what makes it
take effect straight away.
"""

from __future__ import annotations

import json
import math
import uuid

from standardphysics_contracts import NodeMove, OwnerWish, Scan, SceneGraph, TurnDownRequest, Vec3, graph_hash

from . import repository as repo
from . import repository_revisions as revisions_repo
from .db import Database
from .errors import ApiProblem
from .scan_routes import scan_or_404

REJECTED_SPOT_INCHES = 18.0
"""How far a turned-down piece has to stay from that spot if it moves at all: about a chair's width, so a nudge
of a few inches does not count as somewhere new."""
MAX_WISHES = 50
"""The most wishes a scan keeps, as `OwnerWishesRequest` allows; the oldest turned-down spots go first."""
INCH = 0.0254


def _spot(graph: SceneGraph, move: NodeMove) -> tuple[str, Vec3]:
    node = next((node for node in graph.nodes if node.id == move.node_id), None)
    if node is None or not node.movable:
        raise ApiProblem(400, "unknown node", need=[str(move.node_id)])
    here = node.transform.position
    return node.label, Vec3(x=here.x + move.delta_translation.x, y=here.y + move.delta_translation.y, z=here.z)


def _not_there(graph: SceneGraph, move: NodeMove) -> OwnerWish:
    label, spot = _spot(graph, move)
    return OwnerWish(kind="not_there", node_id=move.node_id, at=spot, inches=REJECTED_SPOT_INCHES,
                     text=f"Keep the {label.lower()} out of the spot you turned down")


def _same_spot(a: OwnerWish, b: OwnerWish) -> bool:
    if a.at is None or b.at is None or a.node_id != b.node_id:
        return False
    return math.dist((a.at.x, a.at.y), (b.at.x, b.at.y)) <= REJECTED_SPOT_INCHES * INCH


def _merged(saved: list[OwnerWish], added: list[OwnerWish]) -> list[OwnerWish]:
    """The saved wishes plus the new spots, each spot once, trimmed to MAX_WISHES by dropping the oldest spots."""
    wishes = list(saved)
    for wish in added:
        if not any(_same_spot(wish, kept) for kept in wishes):
            wishes.append(wish)
    while len(wishes) > MAX_WISHES:
        oldest_spot = next((index for index, wish in enumerate(wishes) if wish.at is not None), 0)
        wishes.pop(oldest_spot)
    return wishes


def _record(connection, scan_id: uuid.UUID, graph: SceneGraph, body: TurnDownRequest, added: list[OwnerWish]) -> None:
    payload = {
        "source": body.source,
        "model": body.model,
        "graph_hash": graph_hash(graph),
        "turned_down": [move.model_dump(mode="json") for move in body.turned_down],
        "suggestion": [move.model_dump(mode="json") for move in body.suggestion],
        "spots": [wish.model_dump(mode="json") for wish in added],
    }
    connection.execute(
        "INSERT INTO rearrangement_teacher_events (suggestion_id,scan_id,revision,kind,payload_json)"
        " VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), str(scan_id), body.base_revision, "placement_turned_down", json.dumps(payload)),
    )


def turn_down(database: Database, scan_id: uuid.UUID, body: TurnDownRequest) -> Scan:
    with database.transaction() as connection:
        scan_or_404(connection, scan_id)
        row = revisions_repo.get_revision(connection, scan_id, body.base_revision)
        if row is None:
            raise ApiProblem(404, "no such revision")
        graph = revisions_repo.graph_of(row)
        added = [_not_there(graph, move) for move in body.turned_down]
        repo.set_owner_wishes(connection, scan_id, _merged(repo.owner_wishes(connection, scan_id), added))
        _record(connection, scan_id, graph, body, added)
        return scan_or_404(connection, scan_id)
