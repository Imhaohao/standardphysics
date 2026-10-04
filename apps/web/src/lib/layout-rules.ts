import type { Blocked, SceneGraph, SceneNode } from "@/types/contracts";
import {
  DOOR_SWEEP_ACROSS, DOOR_SWEEP_ALONG, FLOOR_MARGIN, HOME_METERS, MAX_TRAVEL_METERS, OVERLAP_TOLERANCE, SWING_KINDS,
  UNCLAIMED_SURFACE, VERTICAL_TOLERANCE,
} from "@/types/geometry-rules";
import { centreOf, distanceOutside, floorPolygon, footprint, type Point, type Polygon, sizedFootprint, touching } from "./footprints";
import {
  applyMoves, carriedAlong, carriedByHand, floorHeight, measuredPosition, type MoveSet, restsOnSomething, ridersOf, surfaceUnder, topOf,
  underside,
} from "./moves";
import { blocksFloor, liesFlat, readsAsWall } from "./room-shell";

/**
 * The hard constraints a browser can check while a piece moves: what it may
 * not overlap, the floor in front of a door, the edge of the floor and how far
 * it may travel from where the scan found it. Each function mirrors the one of
 * the same name in Lane C's constraints module, so the browser and the server
 * agree on what is legal. The rest (unseen floor, room to pull up to a table,
 * the checks themselves) stays with the server, which judges every layout the
 * browser lets through.
 *
 * One rule deliberately differs: the server's door_keep_clear lays a door's
 * square along the world's axes, and `doorKeepClear` lays it in the door's own
 * turned frame, as the server will once that is fixed there.
 */

export type ClientReason = "collided" | "blocked_a_door" | "left_the_floor" | "moved_too_far";

/** The node's footprint pulled in on every side by `tolerance`: a test shape, never something built. */
export function collisionShape(node: SceneNode, tolerance = OVERLAP_TOLERANCE): Polygon {
  return sizedFootprint(node, Math.max(node.dimensions.x - 2 * tolerance, 1e-6), Math.max(node.dimensions.y - 2 * tolerance, 1e-6));
}

/** A laptop on a desk shares the desk's footprint without touching its body. */
export function oneAboveTheOther(a: SceneNode, b: SceneNode): boolean {
  return underside(a) >= topOf(b) - VERTICAL_TOLERANCE || underside(b) >= topOf(a) - VERTICAL_TOLERANCE;
}

/** Each shape gives up half the tolerance, so together two may interpenetrate by the tolerance and no more. */
export function footprintsMeet(a: SceneNode, b: SceneNode): boolean {
  const half = OVERLAP_TOLERANCE / 2;
  return touching(collisionShape(a, half), collisionShape(b, half));
}

export function overlapping(a: SceneNode, b: SceneNode): boolean {
  return footprintsMeet(a, b) && !oneAboveTheOther(a, b);
}

export function swingsOpen(node: SceneNode): boolean {
  return SWING_KINDS.has(node.kind);
}

/**
 * The floor a door sweeps, laid out in the door's own turned frame: half the
 * opening along the wall each way, and the whole opening out from the wall on
 * each side. The opening is the door's longer side across the floor.
 */
export function doorKeepClear(door: SceneNode): Polygon {
  const opening = Math.max(door.dimensions.x, door.dimensions.y);
  const along = 2 * opening * DOOR_SWEEP_ALONG;
  const across = 2 * opening * DOOR_SWEEP_ACROSS;
  return door.dimensions.x >= door.dimensions.y ? sizedFootprint(door, along, across) : sizedFootprint(door, across, along);
}

/** What the rules read from the layout a move started from, the server's `base`. */
export type RuleBase = {
  nodes: Map<string, SceneNode>;
  floorZ: number;
  /** Pieces the scan found standing on another piece, like a register on a counter. */
  onSurfaces: Set<string>;
  /** The floor's outline, when the scan has a floor. */
  floor: Polygon | null;
};

export function ruleBase(base: SceneGraph): RuleBase {
  const floorZ = floorHeight(base);
  const floorNode = base.nodes.find(liesFlat);
  const standingOnSomething = base.nodes.filter((node) => restsOnSomething(node, floorZ) && surfaceUnder(base, node, floorZ) > floorZ);
  return {
    nodes: new Map(base.nodes.map((node) => [node.id, node])),
    floorZ,
    onSurfaces: new Set(standingOnSomething.map((node) => node.id)),
    floor: floorNode ? floorPolygon(floorNode) : null,
  };
}

/** Two pieces that both stood on a surface clash wherever their footprints meet; others only where their heights overlap too. */
export function collide(base: RuleBase, node: SceneNode, other: SceneNode): boolean {
  if (base.onSurfaces.has(node.id) && base.onSurfaces.has(other.id)) return footprintsMeet(node, other);
  return overlapping(node, other);
}

export type Clash = (node: SceneNode, other: SceneNode) => boolean;

/** Whether the two already clashed where the move started: only a clash the move causes counts. */
export function already(base: RuleBase, clash: Clash, node: SceneNode, other: SceneNode): boolean {
  const was = base.nodes.get(node.id);
  return was !== undefined && clash(was, base.nodes.get(other.id) ?? other);
}

/** Whether a piece stands where the scan found it, give or take a centimetre. */
export function atScannedSpot(base: RuleBase, node: SceneNode, centre: Point = centreOf(node)): boolean {
  const scanned = measuredPosition(base.nodes.get(node.id) ?? node);
  return Math.hypot(centre.x - scanned.x, centre.y - scanned.y) <= HOME_METERS;
}

function turnOf(node: SceneNode): number {
  return Math.atan2(node.transform.m[4], node.transform.m[0]);
}

/** Whether the piece faces the way it did where the move started. */
function unturned(base: RuleBase, node: SceneNode): boolean {
  const was = base.nodes.get(node.id);
  if (!was) return true;
  const turned = turnOf(node) - turnOf(was);
  return Math.abs(Math.atan2(Math.sin(turned), Math.cos(turned))) < 1e-9;
}

/**
 * Whether the piece is back where the scan found it, facing the way it faced.
 * The server's _as_scanned compares positions only, so a piece turned in place
 * still counts there, and the server lets it swing into a wall. Here a turn
 * means it has not been put back.
 */
export function putBack(base: RuleBase, node: SceneNode, centre: Point = centreOf(node)): boolean {
  return atScannedSpot(base, node, centre) && unturned(base, node);
}

/** A piece put back where the scan found it, against one also where the scan found it: the overlap is the scan's. */
export function asScanned(base: RuleBase, node: SceneNode, other: SceneNode): boolean {
  return putBack(base, node) && putBack(base, other);
}

/** Only something standing on the floor gets in the way of a door. */
export function inSwing(base: RuleBase, node: SceneNode, door: SceneNode): boolean {
  return !restsOnSomething(node, base.floorZ) && touching(collisionShape(node), doorKeepClear(door));
}

/** Whether `other` is something the moving piece can run into. Pieces moved earlier always count, as the server checks moved pieces against each other. */
export function isObstacle(base: RuleBase, other: SceneNode, movedIds: Set<string>): boolean {
  if (movedIds.has(other.id)) return true;
  return other.raw_category !== UNCLAIMED_SURFACE && (blocksFloor(other) || readsAsWall(other) || base.onSurfaces.has(other.id));
}

/** How far the piece's corners sit past the floor's edge, counting nothing within the floor margin. */
export function outsideBy(floor: Polygon, node: SceneNode): number {
  return Math.max(...footprint(node).map((corner) => distanceOutside(floor, corner, FLOOR_MARGIN)));
}

/** How far past the floor's edge a piece may go: no further than the scan found it, plus the margin. */
export function floorAllowance(base: RuleBase, floor: Polygon, node: SceneNode): number {
  const was = base.nodes.get(node.id);
  return (was ? outsideBy(floor, was) : 0) + FLOOR_MARGIN;
}

/** Furniture too big to carry has a travel limit. A built-in piece moving is construction, which has none. */
export function hasTravelLimit(node: SceneNode): boolean {
  return node.movable && !carriedByHand(node);
}

/** Where the travel limit is measured from: where the scan found the piece, before any saved layout moved it. */
export function travelOrigin(base: RuleBase, node: SceneNode): Point {
  return measuredPosition(base.nodes.get(node.id) ?? node);
}

export function travelled(base: RuleBase, node: SceneNode): number {
  const origin = travelOrigin(base, node);
  const here = centreOf(node);
  return Math.hypot(here.x - origin.x, here.y - origin.y);
}

/** A layout being judged: the base it started from, the pieces as they stand now and which of them have moved. */
export type LayoutState = { base: RuleBase; shown: SceneGraph; movedIds: Set<string> };

function blocked(node: SceneNode, reason: ClientReason, detail = node.label): Blocked {
  return { node_id: node.id, reason, detail };
}

function runsInto(state: LayoutState, node: SceneNode, other: SceneNode): boolean {
  const { base } = state;
  return collide(base, node, other) && !already(base, (a, b) => collide(base, a, b), node, other) && !asScanned(base, node, other);
}

function blocksTheDoor(base: RuleBase, node: SceneNode, door: SceneNode): boolean {
  return inSwing(base, node, door) && !already(base, (a, b) => inSwing(base, a, b), node, door);
}

/** The first thing the piece runs into, then the first door it stands in front of, as the server names them. */
function clashOf(state: LayoutState, node: SceneNode, checked: Set<string>): Blocked | null {
  const others = state.shown.nodes.filter((other) => !checked.has(other.id) && isObstacle(state.base, other, state.movedIds));
  const hit = others.find((other) => runsInto(state, node, other));
  if (hit) return blocked(node, "collided", `${node.label} into ${hit.label}`);
  const door = state.shown.nodes.find((other) => swingsOpen(other) && blocksTheDoor(state.base, node, other));
  return door ? blocked(node, "blocked_a_door", `${node.label} into the ${door.label}`) : null;
}

function offTheFloor(state: LayoutState, node: SceneNode): Blocked | null {
  const floor = state.base.floor;
  if (!floor) return null;
  return outsideBy(floor, node) > floorAllowance(state.base, floor, node) ? blocked(node, "left_the_floor") : null;
}

function travelledTooFar(state: LayoutState, node: SceneNode): Blocked | null {
  return hasTravelLimit(node) && travelled(state.base, node) > MAX_TRAVEL_METERS ? blocked(node, "moved_too_far") : null;
}

/**
 * Every rule the checked pieces break where they stand in `state.shown`: the
 * floor's edge, a collision or a door, and the travel limit, in the order the
 * server lists them. Pieces checked together, like a counter and the register
 * riding on it, move as one and are not tested against each other.
 */
export function breaches(state: LayoutState, checkedIds: string[]): Blocked[] {
  const checked = new Set(checkedIds);
  const nodes = state.shown.nodes.filter((node) => checked.has(node.id));
  return nodes.flatMap((node) => [offTheFloor(state, node), clashOf(state, node, checked), travelledTooFar(state, node)])
    .filter((found): found is Blocked => found !== null);
}

function breachKey(found: Blocked): string {
  return `${found.node_id}|${found.reason}|${found.detail}`;
}

/** What `after` breaks that `before` did not: a piece already in trouble may still move, so long as the move adds nothing. */
export function newBreaches(before: Blocked[], after: Blocked[]): Blocked[] {
  const known = new Set(before.map(breachKey));
  return after.filter((found) => !known.has(breachKey(found)));
}

/** The pieces that move with `nodeId`: itself and whatever rides on it without a move of its own. */
export function movingWith(base: SceneGraph, moves: MoveSet, nodeId: string): string[] {
  const node = base.nodes.find((candidate) => candidate.id === nodeId);
  const riders = node ? ridersOf(base, node).filter((rider) => !(rider.id in moves)) : [];
  return [nodeId, ...riders.map((rider) => rider.id)];
}

/** The layout `moves` makes of `base`, as the rules judge it. */
export function layoutState(rules: RuleBase, base: SceneGraph, moves: MoveSet): LayoutState {
  return { base: rules, shown: applyMoves(base, moves), movedIds: new Set(Object.keys(carriedAlong(base, moves))) };
}

/** What changing the layout from `before` to `after` newly breaks for `nodeId` and whatever rides on it. */
export function refusedChange(rules: RuleBase, base: SceneGraph, before: MoveSet, after: MoveSet, nodeId: string): Blocked[] {
  const ids = movingWith(base, after, nodeId);
  return newBreaches(breaches(layoutState(rules, base, before), ids), breaches(layoutState(rules, base, after), ids));
}
