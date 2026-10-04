import { convexHull, edgesOf, type Point, type Polygon } from "./footprints";

/**
 * Where a piece's centre may go while it slides without turning.
 *
 * A sliding piece meets an obstacle exactly when its centre enters the
 * obstacle grown by the piece's own outline: the Minkowski sum of the obstacle
 * and the piece mirrored through its centre. Growing each obstacle that way
 * once per drag turns "does this rectangle overlap that one" into "is this
 * point inside that polygon", and a straight step can then say exactly where it
 * first enters and through which edge, which is the surface it slides along.
 */

/** One side of a convex region: inside is where `normal · point < offset`. The normal is a unit vector pointing out. */
export type Edge = { normal: Point; offset: number };

/** A convex region the centre may not enter, with whatever the caller needs to say what it was. */
export type Region<Tag> = { edges: Edge[]; tag: Tag };

/** Where a straight step first enters a region, and the edge it crosses there. */
export type Entry = { t: number; edge: Edge };

/** Below this a step runs along an edge rather than into it. */
const PARALLEL = 1e-12;

export const add = (a: Point, b: Point): Point => ({ x: a.x + b.x, y: a.y + b.y });
export const subtract = (a: Point, b: Point): Point => ({ x: a.x - b.x, y: a.y - b.y });
export const scale = (a: Point, by: number): Point => ({ x: a.x * by, y: a.y * by });
export const dot = (a: Point, b: Point): number => a.x * b.x + a.y * b.y;
export const length = (a: Point): number => Math.hypot(a.x, a.y);

/** The obstacle grown by the piece: every point the piece's centre may not reach. `piece` is drawn about its own centre. */
export function grown(obstacle: Polygon, piece: Polygon): Polygon {
  return convexHull(obstacle.flatMap((corner) => piece.map((point) => subtract(corner, point))));
}

function outwardEdge([start, end]: [Point, Point]): Edge | null {
  const run = subtract(end, start);
  const size = length(run);
  if (size === 0) return null;
  const normal = { x: run.y / size, y: -run.x / size };
  return { normal, offset: dot(normal, start) };
}

/** The edges of an anticlockwise convex outline, or none when it has no area to enter. */
export function edgesOfOutline(outline: Polygon): Edge[] {
  if (outline.length < 3) return [];
  return edgesOf(outline).map(outwardEdge).filter((edge): edge is Edge => edge !== null);
}

/** How deep a point sits inside a region: the distance to its nearest side, negative outside. */
export function depthIn(edges: Edge[], point: Point): number {
  return Math.min(...edges.map((edge) => edge.offset - dot(edge.normal, point)));
}

type Span = { enter: number; exit: number; edge: Edge | null };

/** How far past a region's surface a step has to reach before it counts as going in, so rounding never stops a step that only grazes it. */
const GRAZE = 1e-9;

function clipped(span: Span, edge: Edge, from: Point, step: Point, sink: number): Span | null {
  const gap = dot(edge.normal, from) - edge.offset + sink;
  const rate = dot(edge.normal, step);
  if (Math.abs(rate) < PARALLEL) return gap < 0 ? span : null;
  const t = -gap / rate;
  if (rate > 0) return { ...span, exit: Math.min(span.exit, t) };
  return t > span.enter ? { ...span, enter: t, edge } : span;
}

function spanInside(edges: Edge[], from: Point, step: Point, sink: number): Span | null {
  let span: Span | null = { enter: -Infinity, exit: Infinity, edge: null };
  for (const edge of edges) {
    span = clipped(span, edge, from, step, sink);
    if (span === null) return null;
  }
  return span;
}

function crosses(span: Span | null): span is Span & { edge: Edge } {
  return span !== null && span.edge !== null && span.enter < span.exit && span.enter <= 1 && span.exit > 0;
}

/**
 * Where a step from `from` reaches the region's surface, sunk `sink` metres
 * in, by clipping the step against each side in turn (Cyrus and Beck). A step
 * counts only if it would go on past that surface: one that runs along a side,
 * or leaves the region, never enters it.
 */
export function entry(edges: Edge[], from: Point, step: Point, sink: number): Entry | null {
  const deep = spanInside(edges, from, step, sink + GRAZE);
  if (!crosses(deep)) return null;
  const surface = spanInside(edges, from, step, sink);
  const reached = crosses(surface) ? surface : deep;
  return { t: Math.min(1, Math.max(0, reached.enter)), edge: reached.edge };
}

/**
 * How far along `direction` a point touching `contact` may go before that
 * side of the region ends: past the corner it no longer holds the piece back,
 * so the slide stops there and turns toward the target again.
 */
export function sideEnds(edges: Edge[], contact: Edge, at: Point, direction: Point, sink: number): number {
  return edges
    .filter((edge) => edge !== contact && dot(edge.normal, direction) > PARALLEL)
    .reduce((nearest, edge) => Math.min(nearest, Math.max(0, -(dot(edge.normal, at) - edge.offset + sink) / dot(edge.normal, direction))), Infinity);
}

/** How close to a side a point has to be to count as resting against it. */
const ON_SIDE = 1e-7;

/**
 * The sides of a region a point rests against that a step pushes into. At a
 * corner there are two, and sliding along either one keeps the point outside.
 */
export function sidesPushedInto(edges: Edge[], at: Point, step: Point, sink: number): Edge[] {
  const gaps = edges.map((edge) => dot(edge.normal, at) - edge.offset + sink);
  if (gaps.some((gap) => gap > ON_SIDE)) return [];
  return edges.filter((edge, index) => Math.abs(gaps[index]) <= ON_SIDE && dot(edge.normal, step) < 0);
}

/** The step with the part that pushes through a side taken out, leaving the part that runs along it. */
export function alongSide(step: Point, side: Edge): Point {
  return subtract(step, scale(side.normal, dot(side.normal, step)));
}

/** A circle the centre must stay inside, like the travel limit around where the scan found a piece. */
export type Disc = { centre: Point; radius: number };

/** The nearest point to `point` inside the disc. */
export function intoDisc(disc: Disc, point: Point): Point {
  const away = subtract(point, disc.centre);
  const distance = length(away);
  return distance <= disc.radius ? point : add(disc.centre, scale(away, disc.radius / distance));
}

/** How much of a step from inside a disc stays inside it, as a share of the step. */
export function shareInsideDisc(disc: Disc, from: Point, step: Point): number {
  const a = dot(step, step);
  if (a === 0) return 1;
  const offset = subtract(from, disc.centre);
  const b = 2 * dot(offset, step);
  const c = dot(offset, offset) - disc.radius * disc.radius;
  const leaves = (-b + Math.sqrt(Math.max(0, b * b - 4 * a * c))) / (2 * a);
  return Math.max(0, Math.min(1, leaves));
}
