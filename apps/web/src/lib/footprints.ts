import type { SceneNode } from "@/types/contracts";

/**
 * Floor outlines in room metres, as the pipeline's footprints module draws
 * them. The browser checks a dragged piece with the same shapes and the same
 * tests the server's hard constraints use, so the two agree on what touches.
 */

export type Point = { x: number; y: number };
export type Polygon = Point[];
export type Bounds = { minX: number; minY: number; maxX: number; maxY: number };

/** Square metres below which an outline is a point or a line, not a region. */
const DEGENERATE_AREA = 1e-9;

/** Cosine and sine of the node's turn about Z, from its transform. */
export function rotationAboutZ(node: SceneNode): [number, number] {
  const m = node.transform.m;
  const scale = Math.hypot(m[0], m[4]);
  return scale === 0 ? [1, 0] : [m[0] / scale, m[4] / scale];
}

/** Where the node stands on the floor. */
export function centreOf(node: SceneNode): Point {
  return { x: node.transform.m[3], y: node.transform.m[7] };
}

/** The node's floor rectangle at another size, about the same centre and turned the same way. */
export function sizedFootprint(node: SceneNode, sizeX: number, sizeY: number): Polygon {
  const [cos, sin] = rotationAboutZ(node);
  const centre = centreOf(node);
  const [halfX, halfY] = [sizeX / 2, sizeY / 2];
  const corners: [number, number][] = [[-halfX, -halfY], [halfX, -halfY], [halfX, halfY], [-halfX, halfY]];
  return corners.map(([localX, localY]) => ({ x: centre.x + localX * cos - localY * sin, y: centre.y + localX * sin + localY * cos }));
}

/** The node's floor rectangle, turned about Z, in room coordinates. */
export function footprint(node: SceneNode): Polygon {
  return sizedFootprint(node, node.dimensions.x, node.dimensions.y);
}

function cornerOnFloor(m: number[], local: [number, number, number]): Point {
  const [x, y, z] = local;
  return { x: m[0] * x + m[1] * y + m[2] * z + m[3], y: m[4] * x + m[5] * y + m[6] * z + m[7] };
}

/** The horizontal outline of a floor node: all eight corners of its box, seen from above, as a convex hull. */
export function floorPolygon(node: SceneNode): Polygon {
  const [halfX, halfY, halfZ] = [node.dimensions.x / 2, node.dimensions.y / 2, node.dimensions.z / 2];
  const corners = [-halfX, halfX].flatMap((x) => [-halfY, halfY].flatMap((y) => [-halfZ, halfZ].map((z) => cornerOnFloor(node.transform.m, [x, y, z]))));
  return convexHull(corners);
}

function turn(origin: Point, first: Point, second: Point): number {
  return (first.x - origin.x) * (second.y - origin.y) - (first.y - origin.y) * (second.x - origin.x);
}

function halfHull(points: Point[]): Point[] {
  const hull: Point[] = [];
  for (const point of points) {
    while (hull.length >= 2 && turn(hull[hull.length - 2], hull[hull.length - 1], point) <= 0) hull.pop();
    hull.push(point);
  }
  return hull;
}

function sortedUnique(points: Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  return sorted.filter((point, index) => index === 0 || point.x !== sorted[index - 1].x || point.y !== sorted[index - 1].y);
}

/** Andrew's monotone chain: an anticlockwise outline with no repeated or collinear corners. */
export function convexHull(points: Point[]): Polygon {
  const unique = sortedUnique(points);
  if (unique.length <= 2) return unique;
  const lower = halfHull(unique);
  const upper = halfHull([...unique].reverse());
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

export function edgesOf(polygon: Polygon): [Point, Point][] {
  return polygon.map((point, index) => [point, polygon[(index + 1) % polygon.length]]);
}

/** Positive when the outline runs anticlockwise. */
export function signedArea(polygon: Polygon): number {
  return edgesOf(polygon).reduce((sum, [start, end]) => sum + start.x * end.y - end.x * start.y, 0) / 2;
}

export function polygonBounds(polygon: Polygon): Bounds {
  const xs = polygon.map((point) => point.x);
  const ys = polygon.map((point) => point.y);
  return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
}

export function boundsMeet(a: Bounds, b: Bounds): boolean {
  return a.minX <= b.maxX && b.minX <= a.maxX && a.minY <= b.maxY && b.minY <= a.maxY;
}

function projectedRange(polygon: Polygon, axis: Point): [number, number] {
  const projected = polygon.map((point) => axis.x * point.x + axis.y * point.y);
  return [Math.min(...projected), Math.max(...projected)];
}

function separatedAlong(a: Polygon, b: Polygon, axis: Point): boolean {
  const [aLow, aHigh] = projectedRange(a, axis);
  const [bLow, bHigh] = projectedRange(b, axis);
  return aHigh < bLow || bHigh < aLow;
}

/** The separating axis test over both outlines' edge normals. Shapes that only touch are not separated. */
function separated(a: Polygon, b: Polygon): boolean {
  return [a, b].some((polygon) => edgesOf(polygon).some(([start, end]) => separatedAlong(a, b, { x: -(end.y - start.y), y: end.x - start.x })));
}

/** Whether two convex outlines touch or overlap. */
export function touching(a: Polygon, b: Polygon): boolean {
  return boundsMeet(polygonBounds(a), polygonBounds(b)) && !separated(a, b);
}

function outsideEdge(point: Point, [start, end]: [Point, Point], direction: number, margin: number): boolean {
  const [edgeX, edgeY] = [end.x - start.x, end.y - start.y];
  const cross = edgeX * (point.y - start.y) - edgeY * (point.x - start.x);
  return direction * cross < -margin * Math.hypot(edgeX, edgeY);
}

/** Whether a point is inside a convex outline, allowing `margin` of slack past each edge. An outline with no area holds nothing. */
export function containsPoint(polygon: Polygon, point: Point, margin = 0): boolean {
  const area = polygon.length >= 3 ? signedArea(polygon) : 0;
  if (Math.abs(area) <= DEGENERATE_AREA) return false;
  const direction = area >= 0 ? 1 : -1;
  return !edgesOf(polygon).some((edge) => outsideEdge(point, edge, direction, margin));
}

export function pointToSegment(point: Point, a: Point, b: Point): number {
  const [dx, dy] = [b.x - a.x, b.y - a.y];
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Math.hypot(point.x - a.x, point.y - a.y);
  const t = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSquared));
  return Math.hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy));
}

/** How far a point sits beyond a convex outline's edge, or zero when it is within `margin` of being inside. */
export function distanceOutside(polygon: Polygon, point: Point, margin = 0): number {
  if (polygon.length < 3 || containsPoint(polygon, point, margin)) return 0;
  return Math.min(...edgesOf(polygon).map(([start, end]) => pointToSegment(point, start, end)));
}
