"""Turn matched and unmatched regions into the change records the report and viewer read."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import language
from .landmarks import Landmark, crossed, heading
from .matching import Move
from .regions import Region


@dataclass
class Change:
    id: str
    type: str
    name: str
    detail: str
    sentence: str
    before: Region | None
    after: Region | None
    where_before: str = ""
    where_after: str = ""
    distance_m: float = 0.0
    turn_deg: float | None = None
    similarity: float | None = None

    @property
    def regions(self) -> list[Region]:
        return [region for region in (self.before, self.after) if region is not None]

    @property
    def subject(self) -> Region:
        return max(self.regions, key=lambda region: region.seed_count)


def _route(move: Move, landmarks: list[Landmark]) -> language.Route:
    start, end = move.removed.box.center, move.added.box.center
    return language.Route(
        before=move.removed.names.get("where", ""), after=move.added.names.get("where", ""),
        crossed=crossed(landmarks, start, end), heading=heading(landmarks, start, end),
    )


def _moved(move: Move, landmarks: list[Landmark]) -> Change:
    subject = max((move.removed, move.added), key=lambda region: region.seed_count)
    name = subject.names.get("name", "object")
    where_before = move.removed.names.get("where", "")
    where_after = move.added.names.get("where", "")
    distance = round(move.distance_m, 2)
    return Change(
        id="", type="moved", name=name, detail=subject.names.get("detail", name),
        sentence=language.moved_sentence(name, distance, move.turn_deg, _route(move, landmarks)),
        before=move.removed, after=move.added, where_before=where_before, where_after=where_after,
        distance_m=distance, turn_deg=move.turn_deg, similarity=move.similarity,
    )


def _removed(region: Region) -> Change:
    name, detail, where = (region.names.get(key, "") for key in ("name", "detail", "where"))
    return Change(id="", type="removed", name=name or "object", detail=detail or "object",
                  sentence=language.removed_sentence(detail or "object", where), before=region, after=None,
                  where_before=where)


def _added(region: Region) -> Change:
    name, detail, where = (region.names.get(key, "") for key in ("name", "detail", "where"))
    return Change(id="", type="added", name=name or "object", detail=detail or "object",
                  sentence=language.added_sentence(detail or "object", where), before=None,
                  after=region, where_after=where)


def assemble(moves: list[Move], removed: list[Region], added: list[Region],
             landmarks: list[Landmark] = ()) -> list[Change]:
    """Moves first, then disappearances and appearances, each group largest first."""
    paired = {id(move.removed) for move in moves} | {id(move.added) for move in moves}
    landmarks = [landmark for landmark in landmarks if not landmark.ambiguous]
    changes = [_moved(move, landmarks) for move in sorted(moves, key=lambda m: -m.removed.box.volume)]
    changes += [_removed(r) for r in sorted(removed, key=lambda r: -r.box.volume) if id(r) not in paired]
    changes += [_added(r) for r in sorted(added, key=lambda r: -r.box.volume) if id(r) not in paired]
    for number, change in enumerate(changes, start=1):
        change.id = f"c{number}"
    return changes


def confidence(region: Region, through: np.ndarray, agree: np.ndarray) -> float:
    """Share of the region's points that the other video saw straight through, weighted by how often."""
    looked = through + agree
    if looked.sum() == 0:
        return 0.0
    share = float(through.sum() / looked.sum())
    repeat = float(np.clip(np.median(through[through > 0]) / 4, 0, 1)) if np.any(through > 0) else 0.0
    return round(share * (0.5 + 0.5 * repeat), 2)
