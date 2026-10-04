"""Knee and toe clearance under a raised piece, counted the way ADA 2010 306 measures it.

304.3.1 lets a turning space include knee and toe clearance complying with
306, and 305.4 lets a clear floor space do the same. The occupancy grid draws
a table as solid from the floor to its top, so neither ever could.
`space_beneath` records what the mesh saw under each piece. This works out
which of those cells 306 counts, with the section's numbers handed in from the
rule pack, and frees them for the two questions allowed to use them: the
widest clear circle at a point, and the clear floor in front of a counter.
Routes, passing spaces and every other question keep the plain grid.

From each side of a piece, lane by lane inward from its edge, a cell counts
when all of this holds:

- the floor was seen there and in every cell between it and the edge;
- at the edge the space is open up past the knee band, because a top, an
  apron or a panel lower than that at the edge leaves no knee clearance;
- the toe band is open up to the cell, which lies within 25 inches of the edge
  (306.2.2, 306.3.2) and within 6 inches past the knee clearance at 9 inches
  (306.2.4);
- the knee clearance may lose an inch of depth for every 6 inches of height
  (306.3.4), so a panel hanging to 24 inches, 6 inches in from the edge, holds
  the knee clearance at 9 inches to 8.5 inches deep and the toe clearance to
  14.5;
- the lanes counted at that depth make an opening 30 inches wide at least
  (306.2.5, 306.3.5).

Every height loses `HEIGHT_NOISE` before it is compared. A piece frees cells
only for a point outside the side they were counted from, so a circle never
sits under a table, and never reaches in from one side further than that side
allows by borrowing the cells counted from the other.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

import numpy as np
from scipy import ndimage
from standardphysics_contracts import ClearFloorResult, SceneGraph, SceneNode, SpaceBeneath, Vec3

from .floor_coverage import decode_cells
from .occupancy import Grid, blocks_floor, occupancy_excluding
from .space_beneath import PieceFrame, cells_across, decode_centimetres

HEIGHT_NOISE = 0.02
"""Metres taken off every height the mesh reports under a piece before it meets a limit.

The mesh is noisy by a centimetre or two (see `floor_coverage.FLOOR_BAND`),
so a panel that reads 27.4 inches may hang at 26.6, and it is read as hanging
there."""

CIRCLE_REACH = 2.0
"""Metres around a centre searched once knee and toe clearance is counted.

A circle wider than twice this reads as this wide, which is far past any
turning space."""


@dataclass(frozen=True)
class KneeAndToeLimits:
    """ADA 2010 306's numbers in metres, handed in by a check that reads them from the rule pack."""

    toe_top: float
    """306.2.1: toe clearance is the space between the floor and 9 inches."""
    toe_deepest: float
    """306.2.2: toe clearance extends 25 inches under an element at most."""
    toe_past_knee: float
    """306.2.4: toe clearance stops 6 inches past the knee clearance at 9 inches."""
    knee_top: float
    """306.3.1: knee clearance is the space between 9 and 27 inches."""
    knee_deepest: float
    """306.3.2: knee clearance extends 25 inches under an element at most, at 9 inches."""
    knee_reduction: float
    """306.3.4: depth knee clearance may lose for each unit of height, an inch for every 6."""
    narrowest: float
    """306.2.5 and 306.3.5: knee and toe clearance are 30 inches wide at least."""


@dataclass(frozen=True)
class KneeAndToeSpace:
    """A clear space measured counting knee and toe clearance, and what it counted."""

    space: ClearFloorResult
    under: tuple[UUID, ...] = ()
    """Pieces whose knee and toe clearance `space` reaches into."""
    if_seen: ClearFloorResult | None = None
    """The same space if the floor the scan missed under a piece turned out clear, when that differs."""
    unseen_under: tuple[UUID, ...] = ()
    """The pieces whose unseen floor `if_seen` counts."""


def counted_cells(beneath: SpaceBeneath, limits: KneeAndToeLimits, floor_assumed_clear: bool = False) -> np.ndarray:
    """The cells 306 counts from each side, a stack of four: the piece's local -y, +y, -x and +x sides.

    With `floor_assumed_clear`, floor the mesh never saw is taken to be clear.
    That says what another look could add, never what the scan shows.
    """
    seen = decode_cells(beneath.floor_seen, beneath.rows, beneath.columns)
    if floor_assumed_clear:
        seen = np.ones_like(seen)
    open_to = decode_centimetres(beneath.open_cm, beneath.rows, beneath.columns) - HEIGHT_NOISE
    cell = beneath.cell_size
    wide = cells_across(limits.narrowest, cell)
    return np.stack([
        _put_back(_counted_from_edge(_seen_from(seen, side), _seen_from(open_to, side), limits, cell, wide), side)
        for side in range(4)
    ])


def _seen_from(cells: np.ndarray, side: int) -> np.ndarray:
    """The grid turned so `side` is row 0 and rows run inward from it."""
    return (cells, cells[::-1], cells.T, cells.T[::-1])[side]


def _put_back(view: np.ndarray, side: int) -> np.ndarray:
    """`_seen_from` undone."""
    return (view, view[::-1], view.T, view[::-1].T)[side]


def _counted_from_edge(
    seen: np.ndarray, open_to: np.ndarray, limits: KneeAndToeLimits, cell: float, wide: int
) -> np.ndarray:
    """Which cells count, rows running inward from the edge and lanes across it."""
    depths = np.arange(seen.shape[0])[:, None] * cell
    toe = _leading(seen & (open_to >= limits.toe_top)) * cell
    knee = np.minimum(_knee_depth(open_to, depths, limits), limits.knee_deepest)
    reach = np.minimum(np.minimum(toe, knee + limits.toe_past_knee), limits.toe_deepest)
    knees_fit = seen[0] & (open_to[0] >= limits.knee_top)
    lanes = np.where(knees_fit, np.floor(reach / cell + 1e-9), 0)
    return wide_enough(np.arange(seen.shape[0])[:, None] < lanes[None, :], wide)


def _leading(mask: np.ndarray) -> np.ndarray:
    """How many cells in from the edge each lane stays true for."""
    return np.where(mask.all(axis=0), mask.shape[0], mask.argmin(axis=0))


def _knee_depth(open_to: np.ndarray, depths: np.ndarray, limits: KneeAndToeLimits) -> np.ndarray:
    """How deep each lane's knee clearance at 9 inches may count.

    The nearest surface lower than the top of the knee band sets it: a surface
    at height h, d in from the edge, allows d plus the inch per 6 inches of
    height 306.3.4 lets the clearance lean back by between 9 inches and h.
    Below 9 inches the surface stops the toe clearance too.
    """
    lean = np.maximum(open_to - limits.toe_top, 0.0) * limits.knee_reduction
    return np.where(open_to < limits.knee_top, depths + lean, np.inf).min(axis=0)


def wide_enough(counted: np.ndarray, wide: int) -> np.ndarray:
    """Only the cells in a run of at least `wide` lanes at their own depth."""
    if wide <= 1:
        return counted
    return ndimage.binary_opening(counted, structure=np.ones((1, wide), dtype=bool))


@dataclass(frozen=True)
class PieceCredit:
    """The cells one piece frees from each side, laid on a window of the room's grid."""

    node_id: UUID
    frame: PieceFrame
    rows: slice
    columns: slice
    seen: np.ndarray
    """Four layers, one per side as `counted_cells` orders them, of cells the scan shows count."""
    possible: np.ndarray
    """The same, were the floor the scan missed under the piece clear."""

    def facing(self, point: Vec3) -> list[int]:
        """The sides `point` stands outside of: the only sides it may reach under the piece from."""
        local = self.frame.to_local(np.asarray([[point.x, point.y, 0.0]]), 0.0)[0]
        outside = (
            local[1] < -self.frame.half_y, local[1] > self.frame.half_y,
            local[0] < -self.frame.half_x, local[0] > self.frame.half_x,
        )
        return [side for side, beyond in enumerate(outside) if beyond]


def credits_for(graph: SceneGraph, grid: Grid, limits: KneeAndToeLimits) -> list[PieceCredit]:
    """Every piece with knee and toe clearance the scan saw, or might have, laid on `grid`.

    None on a grid with nothing walkable, which is how the grid says the room
    itself measured nothing.
    """
    if grid.occupied.all():
        return []
    found = (_credit(graph, grid, node, limits) for node in graph.nodes if _has_evidence(node))
    return [credit for credit in found if credit is not None]


def _has_evidence(node: SceneNode) -> bool:
    """Whether the piece carries a record of the space under it that still fits the piece."""
    beneath = node.space_beneath
    return (
        beneath is not None
        and blocks_floor(node)
        and beneath.columns == cells_across(node.dimensions.x, beneath.cell_size)
        and beneath.rows == cells_across(node.dimensions.y, beneath.cell_size)
    )


def _credit(graph: SceneGraph, grid: Grid, node: SceneNode, limits: KneeAndToeLimits) -> PieceCredit | None:
    beneath = node.space_beneath
    assert beneath is not None
    possible = counted_cells(beneath, limits, floor_assumed_clear=True)
    if not possible.any():
        return None
    frame = PieceFrame.of(node)
    rows, columns = _window(grid, frame)
    if rows.start >= rows.stop or columns.start >= columns.stop:
        return None
    layer = _Layer.of(grid, frame, beneath, rows, columns)
    others = occupancy_excluding(graph, grid, node.id, rows, columns)
    return PieceCredit(
        node_id=node.id, frame=frame, rows=rows, columns=columns,
        seen=layer.laid(counted_cells(beneath, limits)) & ~others,
        possible=layer.laid(possible) & ~others,
    )


def _window(grid: Grid, frame: PieceFrame) -> tuple[slice, slice]:
    """The rows and columns of the grid under the piece's footprint."""
    x0, y0, x1, y1 = frame.bounds()
    row0, column0 = grid.to_cell(x0, y0)
    row1, column1 = grid.to_cell(x1, y1)
    rows, columns = grid.shape
    return slice(max(row0, 0), min(row1 + 1, rows)), slice(max(column0, 0), min(column1 + 1, columns))


@dataclass(frozen=True)
class _Layer:
    """Which cell of a piece's own grid each room cell in its window looks up, and which lie on the piece at all."""

    rows: np.ndarray
    columns: np.ndarray
    on_piece: np.ndarray

    @classmethod
    def of(cls, grid: Grid, frame: PieceFrame, beneath: SpaceBeneath, rows: slice, columns: slice) -> _Layer:
        xs = grid.origin_x + (np.arange(columns.start, columns.stop) + 0.5) * grid.cell_size
        ys = grid.origin_y + (np.arange(rows.start, rows.stop) + 0.5) * grid.cell_size
        world_x, world_y = np.meshgrid(xs, ys)
        local = frame.to_local(np.stack([world_x, world_y, np.zeros_like(world_x)], axis=-1), 0.0)
        on_piece = (np.abs(local[..., 0]) <= frame.half_x) & (np.abs(local[..., 1]) <= frame.half_y)
        piece_columns = np.floor((local[..., 0] + frame.half_x) / beneath.cell_size).astype(int)
        piece_rows = np.floor((local[..., 1] + frame.half_y) / beneath.cell_size).astype(int)
        return cls(
            np.clip(piece_rows, 0, beneath.rows - 1), np.clip(piece_columns, 0, beneath.columns - 1), on_piece,
        )

    def laid(self, stack: np.ndarray) -> np.ndarray:
        """A stack of per-side cells moved onto the room's grid."""
        return stack[:, self.rows, self.columns] & self.on_piece


@dataclass(frozen=True)
class Freed:
    """The cells of a window of the room's grid one piece freed."""

    node_id: UUID
    rows: slice
    columns: slice
    cells: np.ndarray


def freed_toward(credits: list[PieceCredit], point: Vec3, floor_assumed_clear: bool = False) -> list[Freed]:
    """The cells every piece frees for a space centred on `point`, from the sides that face it.

    With `floor_assumed_clear`, each piece's cells include those that count
    only if the floor the scan missed is clear.
    """
    freed = []
    for credit in credits:
        sides = credit.facing(point)
        if not sides:
            continue
        stack = credit.possible if floor_assumed_clear else credit.seen
        cells = np.any(stack[sides], axis=0)
        if cells.any():
            freed.append(Freed(credit.node_id, credit.rows, credit.columns, cells))
    return freed


def only_if_seen(credits: list[PieceCredit], point: Vec3) -> list[Freed]:
    """The cells that count for `point` only if the floor the scan missed is clear."""
    seen = {piece.node_id: piece.cells for piece in freed_toward(credits, point)}
    hoped = freed_toward(credits, point, floor_assumed_clear=True)
    return [
        replace(piece, cells=piece.cells & ~seen.get(piece.node_id, np.zeros_like(piece.cells)))
        for piece in hoped
    ]


def with_freed(grid: Grid, freed: list[Freed]) -> Grid:
    """The same grid with the freed cells open."""
    if not freed:
        return grid
    whole = (slice(0, grid.shape[0]), slice(0, grid.shape[1]))
    return replace(grid, occupied=_occupied_within(grid, freed, *whole))


def _occupied_within(grid: Grid, freed: list[Freed], rows: slice, columns: slice) -> np.ndarray:
    """A window of the grid's occupied cells, with the freed ones open."""
    occupied = grid.occupied[rows, columns].copy()
    for piece in freed:
        overlap = _overlap(rows, columns, piece)
        if overlap is not None:
            into, out_of = overlap
            occupied[into] &= ~piece.cells[out_of]
    return occupied


Window = tuple[slice, slice]


def _overlap(rows: slice, columns: slice, piece: Freed) -> tuple[Window, Window] | None:
    """Where a piece's window meets this one, as index pairs into each, or None where they miss."""
    top, bottom = max(rows.start, piece.rows.start), min(rows.stop, piece.rows.stop)
    left, right = max(columns.start, piece.columns.start), min(columns.stop, piece.columns.stop)
    if top >= bottom or left >= right:
        return None
    into = (slice(top - rows.start, bottom - rows.start), slice(left - columns.start, right - columns.start))
    out_of = (
        slice(top - piece.rows.start, bottom - piece.rows.start),
        slice(left - piece.columns.start, right - piece.columns.start),
    )
    return into, out_of


def pieces_at(freed: list[Freed], rows: np.ndarray, columns: np.ndarray) -> tuple[UUID, ...]:
    """The pieces that freed any of these cells."""
    found = []
    for piece in freed:
        local_rows, local_columns = rows - piece.rows.start, columns - piece.columns.start
        height, width = piece.cells.shape
        inside = (local_rows >= 0) & (local_rows < height) & (local_columns >= 0) & (local_columns < width)
        if piece.cells[local_rows[inside], local_columns[inside]].any():
            found.append(piece.node_id)
    return tuple(found)


def widest_circle(grid: Grid, clearance: np.ndarray, freed: list[Freed], at: Vec3) -> float:
    """Metres from `at` to the nearest cell still occupied once the freed cells are open.

    Never less than the plain clearance there, and no more than
    `CIRCLE_REACH` past it unless the plain clearance already is.
    """
    row, column = grid.to_cell(at.x, at.y)
    plain = float(clearance[row, column])
    rows, columns = _around(grid, row, column)
    nearby = [piece for piece in freed if _overlap(rows, columns, piece) is not None]
    if not nearby:
        return plain
    blocked = _occupied_within(grid, nearby, rows, columns)
    if not blocked.any():
        return max(plain, CIRCLE_REACH)
    occupied_rows, occupied_columns = np.nonzero(blocked)
    nearest = np.hypot(occupied_rows + rows.start - row, occupied_columns + columns.start - column).min()
    return max(plain, min(float(nearest) * grid.cell_size, CIRCLE_REACH))


def cells_within(grid: Grid, at: Vec3, radius: float) -> tuple[np.ndarray, np.ndarray]:
    """Every cell whose centre lies closer to `at` than `radius`."""
    row, column = grid.to_cell(at.x, at.y)
    rows, columns = _around(grid, row, column)
    all_rows, all_columns = np.mgrid[rows, columns]
    inside = np.hypot(all_rows - row, all_columns - column) * grid.cell_size < radius
    return all_rows[inside], all_columns[inside]


def _around(grid: Grid, row: int, column: int) -> tuple[slice, slice]:
    reach = int(CIRCLE_REACH / grid.cell_size)
    rows, columns = grid.shape
    return (
        slice(max(row - reach, 0), min(row + reach + 1, rows)),
        slice(max(column - reach, 0), min(column + reach + 1, columns)),
    )
