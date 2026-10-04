import type { SceneGraph, SceneNode } from "@/types/contracts";
import { FLOOR_MARGIN, HOME_METERS, MAX_TRAVEL_METERS } from "@/types/geometry-rules";
import { centreOf, footprint, type Point, type Polygon } from "./footprints";
import {
  already, type ClientReason, collide, doorKeepClear, floorAllowance, hasTravelLimit, inSwing, isObstacle, layoutState,
  movingWith, oneAboveTheOther, putBack, type RuleBase, swingsOpen, travelOrigin,
} from "./layout-rules";
import { type MoveSet, restsOnSomething } from "./moves";
import {
  add, alongSide, depthIn, type Disc, dot, type Edge, edgesOfOutline, entry, grown, intoDisc, length, type Region, scale,
  shareInsideDisc, sideEnds, sidesPushedInto, subtract,
} from "./slide-space";

/**
 * Sliding a piece along whatever it would run into, by the server's rules.
 *
 * Each drag draws the room once for the piece in hand: every footprint it may
 * not overlap and every door's keep-clear square, grown by the piece's own
 * outline, the floor's edges, and the travel limit around where the scan found
 * it. Each pointer move is then one call to `slide`. The piece goes straight
 * for the pointer until it would enter one of those regions, stops on the
 * surface it reached, and spends the rest of the move along that surface,
 * turning toward the pointer again where the surface ends. Nothing has a speed
 * or a mass, so the same pointer path always lands the piece in the same spot.
 *
 * The regions use whole footprints, where the server lets two pieces overlap
 * by its 5 mm tolerance, so a piece slid flush against a wall still sits a
 * tolerance short of anything the server would refuse.
 */

/** What stops a piece: the piece, door, floor edge or travel limit it rests against. */
export type Stop = { reason: ClientReason; nodeId: string; label: string };

type Obstruction = Region<Stop> & {
  /** An overlap the server forgives once the piece is back where the scan found it. */
  forgivenAtHome: boolean;
};

type Limit = Disc & { tag: Stop };

export type SlideSpace = {
  /** The dragged piece's centre when the room was drawn for it. */
  start: Point;
  obstructions: Obstruction[];
  limits: Limit[];
  /** Where the scan found the dragged piece. */
  home: Point;
  /** A piece resting on something is lifted rather than slid: it settles wherever it is set down, and the server judges it there. */
  lifted: boolean;
};

export type Slide = { at: Point; blockedBy: Stop[] };

/** Room the browser keeps short of the server's limits, so rounding never puts a piece a hair past one. */
const SAFETY = 1e-6;
/** Steps shorter than this go nowhere. */
const REACHED = 1e-9;
const MOST_STEPS = 24;

type Piece = { node: SceneNode; outline: Polygon; offset: Point };

/** The piece's outline drawn about the dragged piece's centre, so every region says where that centre may go. */
function pieceAbout(node: SceneNode, reference: Point): Piece {
  return { node, outline: footprint(node).map((corner) => subtract(corner, reference)), offset: subtract(centreOf(node), reference) };
}

function obstruction(outline: Polygon, piece: Piece, tag: Stop, forgivenAtHome = false): Obstruction[] {
  const edges = edgesOfOutline(grown(outline, piece.outline));
  return edges.length > 0 ? [{ edges, tag, forgivenAtHome }] : [];
}

/** What drawing the room for one drag needs: the rules' base, the layout as it stands and which pieces move. */
export type Drawing = { rules: RuleBase; shown: SceneGraph; movedIds: Set<string>; movingIds: Set<string>; draggedId: string };

/** The drawing for dragging `nodeId` in the layout `moves` makes of `base`. */
export function drawingFor(rules: RuleBase, base: SceneGraph, moves: MoveSet, nodeId: string): Drawing {
  const { shown, movedIds } = layoutState(rules, base, moves);
  return { rules, shown, movedIds, movingIds: new Set(movingWith(base, moves, nodeId)), draggedId: nodeId };
}

/** Whether the two can never meet on this drag: one passes over the other, and they are not both up on a surface. */
function passesOver(rules: RuleBase, piece: SceneNode, other: SceneNode): boolean {
  const bothOnSurfaces = rules.onSurfaces.has(piece.id) && rules.onSurfaces.has(other.id);
  return !bothOnSurfaces && oneAboveTheOther(piece, other);
}

function pieceObstructions(drawing: Drawing, piece: Piece, home: Point): Obstruction[] {
  const { rules, shown, movedIds, movingIds } = drawing;
  const clash = (a: SceneNode, b: SceneNode) => collide(rules, a, b);
  const pieceHome = putBack(rules, piece.node, add(home, piece.offset));
  return shown.nodes
    .filter((other) => !movingIds.has(other.id) && isObstacle(rules, other, movedIds))
    .filter((other) => !passesOver(rules, piece.node, other) && !already(rules, clash, piece.node, other))
    .flatMap((other) => obstruction(footprint(other), piece, { reason: "collided", nodeId: other.id, label: other.label }, pieceHome && putBack(rules, other)));
}

function doorObstructions(drawing: Drawing, piece: Piece): Obstruction[] {
  const { rules, shown } = drawing;
  if (restsOnSomething(piece.node, rules.floorZ)) return [];
  const blocks = (a: SceneNode, b: SceneNode) => inSwing(rules, a, b);
  return shown.nodes
    .filter((door) => swingsOpen(door) && !already(rules, blocks, piece.node, door))
    .flatMap((door) => obstruction(doorKeepClear(door), piece, { reason: "blocked_a_door", nodeId: door.id, label: door.label }));
}

/** How far the piece's outline reaches along a direction from the dragged piece's centre. */
function reach(outline: Polygon, direction: Point): number {
  return Math.max(...outline.map((corner) => dot(corner, direction)));
}

/** Everything past a line: the centre may not go further than `limit` along `normal`. */
function beyond(normal: Point, limit: number, tag: Stop): Obstruction {
  return { edges: [{ normal: scale(normal, -1), offset: -limit }], tag, forgivenAtHome: false };
}

type FloorCorner = { vertex: Point; before: Edge; after: Edge };

function floorCorners(outline: Polygon, edges: Edge[]): FloorCorner[] {
  return edges.map((before, index) => ({ vertex: outline[(index + 1) % outline.length], before, after: edges[(index + 1) % edges.length] }));
}

/**
 * Near a corner of the floor, a piece the scan left past the edge may go no
 * further from the corner than it may go past a side. The server measures that
 * as a distance, a circle round the corner; this cuts the corner with the chord
 * between the circle's two ends, which stays inside the circle.
 */
function cornerCut({ vertex, before, after }: FloorCorner, outline: Polygon, allowance: number, tag: Stop): Obstruction[] {
  const bisector = add(before.normal, after.normal);
  const size = length(bisector);
  if (size < 1e-9) return [];
  const normal = scale(bisector, 1 / size);
  const chordEnd = add(vertex, scale(before.normal, allowance));
  return [beyond(normal, dot(normal, chordEnd) - reach(outline, normal), tag)];
}

/**
 * The floor's edge, for one piece: every corner of it within the margin of the
 * floor's outline, or no further past it than the scan found the piece.
 */
function floorObstructions(drawing: Drawing, piece: Piece): Obstruction[] {
  const floor = drawing.rules.floor;
  if (!floor) return [];
  const edges = edgesOfOutline(floor);
  if (edges.length !== floor.length) return [];
  const allowance = floorAllowance(drawing.rules, floor, piece.node) - SAFETY;
  const tag: Stop = { reason: "left_the_floor", nodeId: piece.node.id, label: "the edge of the floor" };
  const sides = edges.map((edge) => beyond(edge.normal, edge.offset + allowance - reach(piece.outline, edge.normal), tag));
  if (allowance <= FLOOR_MARGIN) return sides;
  return [...sides, ...floorCorners(floor, edges).flatMap((corner) => cornerCut(corner, piece.outline, allowance, tag))];
}

function travelLimit(drawing: Drawing, piece: Piece): Limit[] {
  if (!hasTravelLimit(piece.node)) return [];
  const tag: Stop = { reason: "moved_too_far", nodeId: piece.node.id, label: piece.node.label };
  return [{ centre: subtract(travelOrigin(drawing.rules, piece.node), piece.offset), radius: MAX_TRAVEL_METERS - SAFETY, tag }];
}

/** The room drawn for one drag of `drawing.draggedId` and whatever rides on it. */
export function slideSpace(drawing: Drawing): SlideSpace {
  const dragged = drawing.shown.nodes.find((node) => node.id === drawing.draggedId)!;
  const start = centreOf(dragged);
  const home = travelOrigin(drawing.rules, dragged);
  const pieces = drawing.shown.nodes.filter((node) => drawing.movingIds.has(node.id)).map((node) => pieceAbout(node, start));
  return {
    start,
    home,
    lifted: restsOnSomething(dragged, drawing.rules.floorZ),
    obstructions: pieces.flatMap((piece) => [
      ...pieceObstructions(drawing, piece, home), ...doorObstructions(drawing, piece), ...floorObstructions(drawing, piece),
    ]),
    limits: pieces.flatMap((piece) => travelLimit(drawing, piece)),
  };
}

/** One slide's view of the room: each region sunk to however deep the piece already was in it, so it can always back out. */
type Run = { obstructions: Obstruction[]; sinks: number[]; limits: Limit[] };

function runFrom(space: SlideSpace, from: Point, forgiveAtHome: boolean): Run {
  const obstructions = forgiveAtHome ? space.obstructions.filter((region) => !region.forgivenAtHome) : space.obstructions;
  return {
    obstructions,
    sinks: obstructions.map((region) => Math.max(0, depthIn(region.edges, from))),
    limits: space.limits.map((limit) => ({ ...limit, radius: Math.max(limit.radius, length(subtract(from, limit.centre))) })),
  };
}

/** The share of `step` the piece can take before it first enters a region. */
function freeShare(run: Run, at: Point, step: Point): number {
  return run.obstructions.reduce((share, region, index) => Math.min(share, entry(region.edges, at, step, run.sinks[index])?.t ?? 1), 1);
}

function shareInsideLimits(run: Run, at: Point, step: Point): number {
  return run.limits.reduce((share, limit) => Math.min(share, shareInsideDisc(limit, at, step)), 1);
}

/** The share of `step` the piece can take inside every region and every limit. */
function openShare(run: Run, at: Point, step: Point): number {
  return Math.min(freeShare(run, at, step), shareInsideLimits(run, at, step));
}

/** Each way along a side the piece pushes into, as far as that side runs. */
function alongSides(run: Run, at: Point, desired: Point): Point[] {
  return run.obstructions.flatMap((region, index) => sidesPushedInto(region.edges, at, desired, run.sinks[index]).map((side) => {
    const along = alongSide(desired, side);
    return scale(along, Math.min(1, sideEnds(region.edges, side, at, along, run.sinks[index])));
  }));
}

function onRim(limit: Limit, at: Point): boolean {
  return length(subtract(at, limit.centre)) >= limit.radius - SAFETY;
}

/** Round a travel limit the piece is held at: straight across the circle to its point nearest the target. */
function acrossLimits(run: Run, at: Point, target: Point): Point[] {
  return run.limits.filter((limit) => onRim(limit, at) && length(subtract(target, limit.centre)) > limit.radius)
    .map((limit) => subtract(intoDisc(limit, target), at));
}

/**
 * Where the piece can slide from a contact: along each side it pushes into,
 * or across a travel limit, each as far as nothing stops it. The one that ends
 * nearest the target wins, or none when every way on goes into something.
 */
function bestGlide(run: Run, at: Point, desired: Point, target: Point): Point | null {
  const ends = [...alongSides(run, at, desired), ...acrossLimits(run, at, target)]
    .map((step) => add(at, scale(step, openShare(run, at, step))))
    .filter((end) => length(subtract(end, at)) > REACHED);
  return ends.reduce<Point | null>((best, end) => (best === null || length(subtract(target, end)) < length(subtract(target, best)) ? end : best), null);
}

/** One step of a slide: straight at the target until something is in the way, then along it. */
function advance(run: Run, at: Point, target: Point): Point {
  const desired = subtract(target, at);
  if (length(desired) < REACHED) return at;
  const share = openShare(run, at, desired);
  if (share * length(desired) > REACHED) return add(at, scale(desired, share));
  return bestGlide(run, at, desired, target) ?? at;
}

/** What the piece rests against that keeps it from the target. */
function stopsAt(run: Run, at: Point, target: Point): Stop[] {
  const desired = subtract(target, at);
  if (length(desired) < REACHED) return [];
  const pressed = run.obstructions.filter((region, index) => sidesPushedInto(region.edges, at, desired, run.sinks[index]).length > 0);
  const limits = run.limits.filter((limit) => length(subtract(target, limit.centre)) > limit.radius && onRim(limit, at));
  const stops = [...pressed, ...limits].map((found) => found.tag);
  return stops.filter((stop, index) => stops.findIndex((other) => other.nodeId === stop.nodeId && other.reason === stop.reason) === index);
}

function glideToward(space: SlideSpace, from: Point, target: Point, forgiveAtHome: boolean): Slide {
  const run = runFrom(space, from, forgiveAtHome);
  let at = from;
  for (let step = 0; step < MOST_STEPS; step++) {
    const next = advance(run, at, target);
    if (length(subtract(next, at)) < REACHED) break;
    at = next;
  }
  return { at, blockedBy: stopsAt(run, at, target) };
}

/**
 * Where a piece at `from` ends up when the pointer asks for `target`. Within a
 * centimetre of where the scan found it, the piece goes back exactly there,
 * where the server forgives any overlap the scan itself had.
 */
export function slide(space: SlideSpace, from: Point, target: Point): Slide {
  if (space.lifted) return { at: target, blockedBy: [] };
  const nearHome = length(subtract(target, space.home)) <= HOME_METERS;
  if (nearHome) {
    const home = glideToward(space, from, space.home, true);
    if (length(subtract(home.at, space.home)) < REACHED) return home;
  }
  return glideToward(space, from, target, false);
}
