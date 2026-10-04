import type { Blocked, SceneGraph } from "@/types/contracts";
import type { Point } from "./footprints";
import { refusedChange, type RuleBase } from "./layout-rules";
import { type MoveSet, placedAt, withMove } from "./moves";
import { drawingFor, slide, type SlideSpace, slideSpace, type Stop } from "./slide";

/**
 * A piece in hand. Dragging reports how far the pointer moved, and the piece
 * chases the spot the pointer has reached rather than adding those moves up,
 * so a piece held back by a wall comes away again as soon as the pointer does.
 */
export type HeldPiece = { nodeId: string; space: SlideSpace; wanted: Point; at: Point };

/** The layout the rules start from, and the layout as it stands. */
export type Arranging = { rules: RuleBase; base: SceneGraph; moves: MoveSet };

export function pickUp({ rules, base, moves }: Arranging, nodeId: string): HeldPiece {
  const space = slideSpace(drawingFor(rules, base, moves, nodeId));
  return { nodeId, space, wanted: space.start, at: space.start };
}

export type Pulled = { held: HeldPiece; moves: MoveSet; blockedBy: Stop[] };

function movedAtAll(from: Point, to: Point): boolean {
  return Math.hypot(to.x - from.x, to.y - from.y) > 1e-9;
}

/**
 * The piece after the pointer moves by (dx, dy): as close to the pointer as the
 * room lets it get. The server's own rules check every spot the slide picks,
 * and a spot they would refuse leaves the piece where it was. A piece that does
 * not move hands back the very same moves.
 */
export function pull(arranging: Arranging, held: HeldPiece, dx: number, dy: number): Pulled {
  const wanted = { x: held.wanted.x + dx, y: held.wanted.y + dy };
  const { at, blockedBy } = slide(held.space, held.at, wanted);
  const stays = { held: { ...held, wanted }, moves: arranging.moves, blockedBy };
  if (!movedAtAll(held.at, at)) return stays;
  const moves = placedAt(arranging.base, arranging.moves, held.nodeId, at);
  const refused = !held.space.lifted && refusedChange(arranging.rules, arranging.base, arranging.moves, moves, held.nodeId).length > 0;
  return refused ? stays : { held: { ...held, wanted, at }, moves, blockedBy };
}

/** A change the editor made or turned down, with what it would have broken. */
export type Outcome = { moves: MoveSet; refused: Blocked[] };

/** An arrow key's step: the piece slides as far as it can, and when it cannot move at all, says what is in the way. */
export function nudge(arranging: Arranging, nodeId: string, dx: number, dy: number): Outcome {
  const held = pickUp(arranging, nodeId);
  const pulled = pull(arranging, held, dx, dy);
  if (movedAtAll(held.at, pulled.held.at)) return { moves: pulled.moves, refused: [] };
  const wanted = withMove(arranging.moves, nodeId, dx, dy, 0);
  return { moves: arranging.moves, refused: refusedChange(arranging.rules, arranging.base, arranging.moves, wanted, nodeId) };
}

/** A turn from R or the turn buttons, refused with its reasons when the turned piece would break a rule. */
export function turn(arranging: Arranging, nodeId: string, degrees: number): Outcome {
  const turned = withMove(arranging.moves, nodeId, 0, 0, degrees);
  const refused = refusedChange(arranging.rules, arranging.base, arranging.moves, turned, nodeId);
  return refused.length > 0 ? { moves: arranging.moves, refused } : { moves: turned, refused: [] };
}
