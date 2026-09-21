import type { SceneNode } from "@/types/contracts";

export type MotionPoint = { x: number; z: number };

export type ReachProfile = {
  maxReachDistance?: number;
  minReachHeight?: number;
  maxReachHeight?: number;
  handReference?: string | null;
  distanceInterval?: [number, number];
  heightInterval?: [number, number];
};

/** Adjustable navigation estimates, not a model-specific wheelchair measurement. */
export type WheelchairProfile = {
  eyeHeight: number;
  speed: number;
  collisionRadius: number;
  reach?: ReachProfile | null;
};

export const WHEELCHAIR_PROFILE_LIMITS = {
  eyeHeight: { min: 0.75, max: 1.45 },
  speed: { min: 0.6, max: 4 },
  collisionRadius: { min: 0.3, max: 0.7 },
  minReachHeight: { min: 0.1, max: 0.8 },
  maxReachHeight: { min: 0.8, max: 1.8 },
  maxReachDistance: { min: 0.2, max: 1.2 },
} as const;

export const DEFAULT_WHEELCHAIR_PROFILE: WheelchairProfile = {
  eyeHeight: 1.15,
  speed: 2.4,
  collisionRadius: 0.45,
  reach: null,
};

function boundedEstimate(value: unknown, limits: { min: number; max: number }, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.min(limits.max, Math.max(limits.min, value));
}

/** Keeps user-entered navigation estimates finite and within the conservative UI range. */
export function wheelchairProfile(profile: Partial<WheelchairProfile> | null | undefined): WheelchairProfile {
  return {
    eyeHeight: boundedEstimate(profile?.eyeHeight, WHEELCHAIR_PROFILE_LIMITS.eyeHeight, DEFAULT_WHEELCHAIR_PROFILE.eyeHeight),
    speed: boundedEstimate(profile?.speed, WHEELCHAIR_PROFILE_LIMITS.speed, DEFAULT_WHEELCHAIR_PROFILE.speed),
    collisionRadius: boundedEstimate(profile?.collisionRadius, WHEELCHAIR_PROFILE_LIMITS.collisionRadius, DEFAULT_WHEELCHAIR_PROFILE.collisionRadius),
    ...(profile?.reach !== undefined ? { reach: profile.reach ? { ...profile.reach } : null } : {}),
  };
}



export type CollisionRect = {
  node: SceneNode;
  center: MotionPoint;
  axisX: MotionPoint;
  axisY: MotionPoint;
  halfX: number;
  halfY: number;
};

export type WheelchairMotionGeometry = {
  floors: CollisionRect[];
  obstacles: CollisionRect[];
  targets: CollisionRect[];
};

export type SweptMove = {
  point: MotionPoint;
  reached: boolean;
};

const EPSILON = 0.0001;
const MIN_SEGMENT = 0.01;
// Some scene exports describe walls and portals as planar outlines. This only gives
// those navigation boundaries a small collision thickness; measured widths remain intact.
const PLANAR_BOUNDARY_THICKNESS = 0.05;

function add(a: MotionPoint, b: MotionPoint): MotionPoint {
  return { x: a.x + b.x, z: a.z + b.z };
}

function subtract(a: MotionPoint, b: MotionPoint): MotionPoint {
  return { x: a.x - b.x, z: a.z - b.z };
}

function scale(point: MotionPoint, amount: number): MotionPoint {
  return { x: point.x * amount, z: point.z * amount };
}

function dot(a: MotionPoint, b: MotionPoint): number {
  return a.x * b.x + a.z * b.z;
}

function length(point: MotionPoint): number {
  return Math.hypot(point.x, point.z);
}

function normalize(point: MotionPoint, fallback: MotionPoint): MotionPoint {
  const magnitude = length(point);
  return magnitude > EPSILON ? scale(point, 1 / magnitude) : fallback;
}

type ProjectedAxis = {
  point: MotionPoint;
  dimension: number;
  scale: number;
};

/**
 * Scene exports may encode a horizontal floor in local X/Y or local X/Z.
 * Select the two local axes that actually span the viewer ground plane rather
 * than assuming a fixed source-up axis.
 */
function horizontalAxes(node: SceneNode, planarBoundary: boolean): ProjectedAxis[] {
  const matrix = node.transform.m;
  const fallbackDimension = planarBoundary ? PLANAR_BOUNDARY_THICKNESS : 0;
  const axes = [
    { point: { x: matrix[0], z: -matrix[4] }, dimension: node.dimensions.x },
    { point: { x: matrix[1], z: -matrix[5] }, dimension: node.dimensions.y },
    { point: { x: matrix[2], z: -matrix[6] }, dimension: node.dimensions.z },
  ].map((axis) => ({ ...axis, scale: length(axis.point), dimension: axis.dimension > EPSILON ? axis.dimension : fallbackDimension }));

  return axes
    .filter((axis) => axis.scale > EPSILON && axis.dimension > EPSILON)
    .sort((left, right) => right.scale * right.dimension - left.scale * left.dimension)
    .slice(0, 2);
}

function sceneRect(node: SceneNode): CollisionRect | null {
  const matrix = node.transform.m;
  const planarBoundary = node.kind === "wall" || node.kind === "door" || node.kind === "opening";
  const axes = horizontalAxes(node, planarBoundary);
  if (axes.length !== 2) return null;
  const [x, y] = axes;
  const halfX = (x.dimension * x.scale) / 2;
  const halfY = (y.dimension * y.scale) / 2;

  if (halfX <= EPSILON || halfY <= EPSILON) return null;

  return {
    node,
    center: { x: matrix[3], z: -matrix[7] },
    axisX: normalize(x.point, { x: 1, z: 0 }),
    axisY: normalize(y.point, { x: 0, z: 1 }),
    halfX,
    halfY,
  };
}

function portalIntervals(wall: CollisionRect, portals: CollisionRect[]): { axis: "x" | "y"; intervals: { start: number; end: number }[] } {
  const axis = wall.halfX >= wall.halfY ? "x" : "y";
  const wallAxis = axis === "x" ? wall.axisX : wall.axisY;
  const acrossAxis = axis === "x" ? wall.axisY : wall.axisX;
  const wallHalfAlong = axis === "x" ? wall.halfX : wall.halfY;
  const wallHalfAcross = axis === "x" ? wall.halfY : wall.halfX;

  const intervals = portals.filter((portal) => portal.node.parent_id === null || portal.node.parent_id === wall.node.id).flatMap((portal) => {
    const offset = subtract(portal.center, wall.center);
    const centerAlong = dot(offset, wallAxis);
    const centerAcross = dot(offset, acrossAxis);
    const portalHalfAlong = Math.abs(dot(portal.axisX, wallAxis)) * portal.halfX + Math.abs(dot(portal.axisY, wallAxis)) * portal.halfY;
    const portalHalfAcross = Math.abs(dot(portal.axisX, acrossAxis)) * portal.halfX + Math.abs(dot(portal.axisY, acrossAxis)) * portal.halfY;

    if (Math.abs(centerAcross) > wallHalfAcross + portalHalfAcross + EPSILON) return [];
    const start = Math.max(-wallHalfAlong, centerAlong - portalHalfAlong);
    const end = Math.min(wallHalfAlong, centerAlong + portalHalfAlong);
    if (end - start <= MIN_SEGMENT) return [];
    const opening = { start, end };
    return opening.end - opening.start > MIN_SEGMENT ? [opening] : [];
  }).sort((left, right) => left.start - right.start);

  const merged = intervals.reduce<{ start: number; end: number }[]>((all, next) => {
    const previous = all[all.length - 1];
    if (previous && next.start <= previous.end + EPSILON) {
      previous.end = Math.max(previous.end, next.end);
      return all;
    }
    all.push({ ...next });
    return all;
  }, []);

  return { axis, intervals: merged };
}

function splitWall(wall: CollisionRect, portals: CollisionRect[]): CollisionRect[] {
  const { axis, intervals } = portalIntervals(wall, portals);
  if (intervals.length === 0) return [wall];

  const wallAxis = axis === "x" ? wall.axisX : wall.axisY;
  const wallHalfAlong = axis === "x" ? wall.halfX : wall.halfY;
  const segments: { start: number; end: number }[] = [];
  let cursor = -wallHalfAlong;

  for (const opening of intervals) {
    if (opening.start - cursor > MIN_SEGMENT) segments.push({ start: cursor, end: opening.start });
    cursor = Math.max(cursor, opening.end);
  }
  if (wallHalfAlong - cursor > MIN_SEGMENT) segments.push({ start: cursor, end: wallHalfAlong });

  return segments.map((segment) => {
    const halfAlong = (segment.end - segment.start) / 2;
    const center = add(wall.center, scale(wallAxis, (segment.start + segment.end) / 2));
    return axis === "x"
      ? { ...wall, center, halfX: halfAlong }
      : { ...wall, center, halfY: halfAlong };
  });
}

/** Builds viewer-plane collision rectangles from scene coordinates. Floors and portals stay passable. */
export function wheelchairMotionGeometry(nodes: SceneNode[]): WheelchairMotionGeometry {
  const rects = nodes.flatMap((node) => {
    const rect = sceneRect(node);
    return rect ? [rect] : [];
  });
  const portals = rects.filter((rect) => rect.node.kind === "door" || rect.node.kind === "opening");
  const walls = rects.filter((rect) => rect.node.kind === "wall").flatMap((wall) => splitWall(wall, portals));
  const targets = rects.filter((rect) => rect.node.kind === "object" || rect.node.kind === "outlet" || rect.node.kind === "candidate_outlet");
  const objects = targets.filter((rect) => rect.node.dimensions.z > EPSILON && rect.node.kind === "object");

  return {
    floors: rects.filter((rect) => rect.node.kind === "floor"),
    obstacles: [...walls, ...objects],
    targets,
  };
}

function closestPoint(rect: CollisionRect, point: MotionPoint): MotionPoint {
  const offset = subtract(point, rect.center);
  const localX = Math.max(-rect.halfX, Math.min(rect.halfX, dot(offset, rect.axisX)));
  const localY = Math.max(-rect.halfY, Math.min(rect.halfY, dot(offset, rect.axisY)));
  return add(rect.center, add(scale(rect.axisX, localX), scale(rect.axisY, localY)));
}

export function distanceToRect(point: MotionPoint, rect: CollisionRect): number {
  return length(subtract(point, closestPoint(rect, point)));
}

export function collidesAt(point: MotionPoint, obstacles: CollisionRect[], radius: number): boolean {
  return obstacles.some((obstacle) => distanceToRect(point, obstacle) < radius - EPSILON);
}

/** Tests if a 2D line segment between a and b penetrates a collision rectangle. */
export function segmentIntersectsRect(a: MotionPoint, b: MotionPoint, rect: CollisionRect): boolean {
  const da = subtract(a, rect.center);
  const db = subtract(b, rect.center);
  const p1x = dot(da, rect.axisX);
  const p1y = dot(da, rect.axisY);
  const p2x = dot(db, rect.axisX);
  const p2y = dot(db, rect.axisY);

  const dx = p2x - p1x;
  const dy = p2y - p1y;

  let t0 = 0.0;
  let t1 = 1.0;

  const clip = (p: number, q: number) => {
    if (Math.abs(p) < EPSILON) {
      if (q < 0) return false;
      return true;
    }
    const r = q / p;
    if (p < 0) {
      if (r > t1) return false;
      if (r > t0) t0 = r;
    } else {
      if (r < t0) return false;
      if (r < t1) t1 = r;
    }
    return true;
  };

  // Shrink slightly so a point terminating on the boundary face of a supporting wall does not penetrate
  const shrinkX = Math.max(0, rect.halfX - 0.005);
  const shrinkY = Math.max(0, rect.halfY - 0.005);

  if (!clip(-dx, p1x - (-shrinkX))) return false;
  if (!clip(dx, shrinkX - p1x)) return false;
  if (!clip(-dy, p1y - (-shrinkY))) return false;
  if (!clip(dy, shrinkY - p1y)) return false;

  return t0 <= t1 && t1 - t0 > 0.001;
}

function sweep(start: MotionPoint, delta: MotionPoint, radius: number, canOccupy: (point: MotionPoint) => boolean, maxStep: number): SweptMove {
  if (!canOccupy(start)) return { point: start, reached: false };
  const total = length(delta);
  if (total <= EPSILON) return { point: start, reached: true };

  const stepSize = Math.min(Math.max(maxStep, EPSILON), Math.max(radius / 2, EPSILON));
  const steps = Math.max(1, Math.ceil(total / stepSize));
  let valid = start;
  for (let step = 1; step <= steps; step += 1) {
    const next = add(start, scale(delta, step / steps));
    if (!canOccupy(next)) return { point: valid, reached: false };
    valid = next;
  }
  return { point: valid, reached: true };
}

/** Moves in bounded increments so a long frame cannot cross a thin wall. */
export function sweepWheelchair(start: MotionPoint, delta: MotionPoint, obstacles: CollisionRect[], radius: number, maxStep = 0.08): SweptMove {
  return sweep(start, delta, radius, (point) => !collidesAt(point, obstacles, radius), maxStep);
}

function containsPoint(rect: CollisionRect, point: MotionPoint, inset = 0): boolean {
  const offset = subtract(point, rect.center);
  return Math.abs(dot(offset, rect.axisX)) <= rect.halfX - inset && Math.abs(dot(offset, rect.axisY)) <= rect.halfY - inset;
}

/** True only for a collision-free point on one of the measured floor surfaces. */
export function canOccupyWheelchair(point: MotionPoint, geometry: WheelchairMotionGeometry, radius: number): boolean {
  const onFloor = geometry.floors.length === 0 || geometry.floors.some((floor) => floor.halfX >= radius && floor.halfY >= radius && containsPoint(floor, point, radius));
  return onFloor && !collidesAt(point, geometry.obstacles, radius);
}

/** Uses the same bounded sweep for manual drive and docking, including floor coverage. */
export function sweepWheelchairInGeometry(start: MotionPoint, delta: MotionPoint, geometry: WheelchairMotionGeometry, radius: number, maxStep = 0.08): SweptMove {
  return sweep(start, delta, radius, (point) => canOccupyWheelchair(point, geometry, radius), maxStep);
}

/** Finds a collision-free path for the wheelchair using direct sweep or A* search on measured floors. */
const GRID_STEP = 0.1;

type PathNode = {
  point: MotionPoint;
  g: number;
  f: number;
  parent: PathNode | null;
};

const GRID_MOVES = [
  { x: GRID_STEP, z: 0, cost: GRID_STEP },
  { x: -GRID_STEP, z: 0, cost: GRID_STEP },
  { x: 0, z: GRID_STEP, cost: GRID_STEP },
  { x: 0, z: -GRID_STEP, cost: GRID_STEP },
  { x: GRID_STEP, z: GRID_STEP, cost: GRID_STEP * Math.SQRT2 },
  { x: GRID_STEP, z: -GRID_STEP, cost: GRID_STEP * Math.SQRT2 },
  { x: -GRID_STEP, z: GRID_STEP, cost: GRID_STEP * Math.SQRT2 },
  { x: -GRID_STEP, z: -GRID_STEP, cost: GRID_STEP * Math.SQRT2 },
];

function gridKey(point: MotionPoint): string {
  return `${Math.round(point.x / GRID_STEP)},${Math.round(point.z / GRID_STEP)}`;
}

/** The open node with the least estimated total cost, lifted out of the queue. */
function takeCheapest(openList: PathNode[]): PathNode {
  let best = 0;
  for (let i = 1; i < openList.length; i++) {
    if (openList[i].f < openList[best].f) best = i;
  }
  return openList.splice(best, 1)[0];
}

/** The route back to the start, and how far the chair travels along it. */
function retrace(last: PathNode, goal: MotionPoint): { path: MotionPoint[]; distance: number } {
  const path: MotionPoint[] = [goal];
  let step: PathNode | null = last;
  while (step) {
    path.unshift(step.point);
    step = step.parent;
  }
  let distance = 0;
  for (let i = 0; i < path.length - 1; i++) {
    distance += length(subtract(path[i + 1], path[i]));
  }
  return { path, distance };
}

/** Every neighbouring cell a chair of this size can roll into from here. */
function reachableNeighbours(
  current: PathNode,
  goal: MotionPoint,
  geometry: WheelchairMotionGeometry,
  radius: number,
  closed: Set<string>,
  gScores: Map<string, number>,
): PathNode[] {
  const found: PathNode[] = [];
  for (const move of GRID_MOVES) {
    const point: MotionPoint = { x: current.point.x + move.x, z: current.point.z + move.z };
    const key = gridKey(point);
    if (closed.has(key)) continue;
    if (!canOccupyWheelchair(point, geometry, radius)) continue;
    if (!sweepWheelchairInGeometry(current.point, subtract(point, current.point), geometry, radius).reached) {
      continue;
    }
    const g = current.g + move.cost;
    const known = gScores.get(key);
    if (known !== undefined && g >= known) continue;
    gScores.set(key, g);
    found.push({ point, g, f: g + length(subtract(goal, point)), parent: current });
  }
  return found;
}

/** Whether the chair can roll straight from here into the goal. */
function finishesFrom(
  current: PathNode,
  goal: MotionPoint,
  geometry: WheelchairMotionGeometry,
  radius: number,
): boolean {
  if (length(subtract(goal, current.point)) > GRID_STEP * 2) return false;
  return sweepWheelchairInGeometry(current.point, subtract(goal, current.point), geometry, radius).reached;
}

export function findWheelchairPath(
  start: MotionPoint,
  goal: MotionPoint,
  geometry: WheelchairMotionGeometry,
  radius: number,
  maxExpansions = 50000,
): { path: MotionPoint[]; reached: boolean; distance: number | null } {
  const straight = sweepWheelchairInGeometry(start, subtract(goal, start), geometry, radius);
  if (straight.reached) {
    return { path: [start, goal], reached: true, distance: length(subtract(goal, start)) };
  }

  const openList: PathNode[] = [
    { point: start, g: 0, f: length(subtract(goal, start)), parent: null },
  ];
  const gScores = new Map<string, number>([[gridKey(start), 0]]);
  const closed = new Set<string>();
  let expansions = 0;

  while (openList.length > 0 && expansions < maxExpansions) {
    const current = takeCheapest(openList);
    const key = gridKey(current.point);
    if (closed.has(key)) continue;
    closed.add(key);
    expansions++;

    if (finishesFrom(current, goal, geometry, radius)) {
      const { path, distance } = retrace(current, goal);
      return { path, reached: true, distance };
    }
    openList.push(...reachableNeighbours(current, goal, geometry, radius, closed, gScores));
  }

  return { path: [], reached: false, distance: null };
}

function floorCandidates(floor: CollisionRect, radius: number): MotionPoint[] {
  const insetX = Math.max(0, floor.halfX - radius);
  const insetY = Math.max(0, floor.halfY - radius);
  return [
    floor.center,
    add(floor.center, add(scale(floor.axisX, insetX * 0.5), scale(floor.axisY, insetY * 0.5))),
    add(floor.center, add(scale(floor.axisX, -insetX * 0.5), scale(floor.axisY, insetY * 0.5))),
    add(floor.center, add(scale(floor.axisX, insetX * 0.5), scale(floor.axisY, -insetY * 0.5))),
    add(floor.center, add(scale(floor.axisX, -insetX * 0.5), scale(floor.axisY, -insetY * 0.5))),
  ];
}

/** Chooses a free point near the requested start, preferring measured floor space. */
export function wheelchairSpawn(preferred: MotionPoint, geometry: WheelchairMotionGeometry, radius: number): MotionPoint | null {
  const candidates: MotionPoint[] = [preferred];
  for (let ring = 0.25; ring <= 2; ring += 0.25) {
    candidates.push(
      { x: preferred.x + ring, z: preferred.z },
      { x: preferred.x - ring, z: preferred.z },
      { x: preferred.x, z: preferred.z + ring },
      { x: preferred.x, z: preferred.z - ring },
    );
  }
  candidates.push(...geometry.floors.flatMap((floor) => floorCandidates(floor, radius)));

  const gridStep = 0.25;
  const addGrid = (center: MotionPoint, axisX: MotionPoint, axisY: MotionPoint, halfX: number, halfY: number) => {
    const xSteps = Math.min(64, Math.floor((halfX * 2) / gridStep));
    const ySteps = Math.min(64, Math.floor((halfY * 2) / gridStep));
    for (let xIndex = 0; xIndex <= xSteps; xIndex += 1) {
      for (let yIndex = 0; yIndex <= ySteps; yIndex += 1) {
        const localX = -halfX + (xIndex / Math.max(xSteps, 1)) * halfX * 2;
        const localY = -halfY + (yIndex / Math.max(ySteps, 1)) * halfY * 2;
        candidates.push(add(center, add(scale(axisX, localX), scale(axisY, localY))));
      }
    }
  };
  if (geometry.floors.length > 0) {
    for (const floor of geometry.floors) {
      if (floor.halfX >= radius && floor.halfY >= radius) addGrid(floor.center, floor.axisX, floor.axisY, floor.halfX - radius, floor.halfY - radius);
    }
  } else {
    addGrid(preferred, { x: 1, z: 0 }, { x: 0, z: 1 }, 2, 2);
  }
  candidates.sort((left, right) => length(subtract(left, preferred)) - length(subtract(right, preferred)));

  return candidates.find((candidate) => canOccupyWheelchair(candidate, geometry, radius)) ?? null;
}

/** Returns a clear point on the side of an object closest to the wheelchair. */
export function dockPoint(from: MotionPoint, target: CollisionRect, radius: number, gap = 0.2): MotionPoint {
  const offset = subtract(from, target.center);
  const localX = dot(offset, target.axisX);
  const localY = dot(offset, target.axisY);
  if (Math.abs(localX) / target.halfX >= Math.abs(localY) / target.halfY) {
    const direction = localX >= 0 ? 1 : -1;
    return add(target.center, scale(target.axisX, direction * (target.halfX + radius + gap)));
  }
  const direction = localY >= 0 ? 1 : -1;
  return add(target.center, scale(target.axisY, direction * (target.halfY + radius + gap)));
}

export type ApproachStatus = "clear" | "blocked" | "needs_verification";
export type ReachStatus = "within_reach" | "outside_reach" | "needs_verification";

export type OutletAccessibilityAssessment = {
  approachStatus: ApproachStatus;
  approachCandidate: MotionPoint | null;
  approachDistance: number | null;
  approachHeadingDeg: number | null;
  reachStatus: ReachStatus;
  targetHeightAboveFloor: number | null;
  reachDistance: number | null;
  unresolvedReasons: string[];
  disclaimers: string[];
};

const OUTLET_DISCLAIMERS = [
  "Electrical power, circuit live status, voltage, and socket condition are not established.",
  "Plug insertion force, dexterity, and grip requirements are not established.",
  "ADA compliance is not established.",
  "Passing modeled reach is not proof of grasp, plug insertion, arm motion, strength or safe independent use.",
];

type TargetGeometry = {
  position: MotionPoint;
  heightAboveFloor: number | null;
  normal: MotionPoint;
  orientationKnown: boolean;
  socketResolved: boolean;
  reasons: string[];
};

/** How far the fitting sits above the modeled floor under it, or null when none is modeled. */
function heightAboveLocalFloor(
  outletNode: SceneNode,
  position: MotionPoint,
  geometry: WheelchairMotionGeometry,
): number | null {
  const floor = geometry.floors.find((f) => containsPoint(f, position, 0.05));
  if (!floor) return null;
  return Math.max(0, outletNode.transform.m[11] - floor.node.transform.m[11]);
}

/** Whether the scan could not pin down where on the faceplate the socket actually is. */
function hasUnresolvedSocket(outletNode: SceneNode): boolean {
  return Boolean(
    outletNode.attachment?.uncertainty_reasons?.some((r) =>
      r.toLowerCase().includes("unresolved socket"),
    ),
  );
}

/** Where the fitting is, how high it sits above the floor beneath it, and which way it faces. */
function outletGeometry(outletNode: SceneNode, geometry: WheelchairMotionGeometry): TargetGeometry {
  const reasons: string[] = [];
  const position: MotionPoint = { x: outletNode.transform.m[3], z: -outletNode.transform.m[7] };

  const heightAboveFloor = heightAboveLocalFloor(outletNode, position, geometry);
  if (heightAboveFloor === null) {
    reasons.push("No modeled floor under target; local floor elevation unknown.");
  }

  const rawNormal = outletNode.attachment?.normal;
  if (!rawNormal) reasons.push("Outlet support normal is missing; orientation unknown.");

  const socketResolved = !hasUnresolvedSocket(outletNode);
  if (!socketResolved) reasons.push("Socket target is unresolved; cannot confirm operable reach.");

  return {
    position,
    heightAboveFloor,
    normal: rawNormal ? normalize({ x: rawNormal.x, z: -rawNormal.y }, { x: 0, z: 1 }) : { x: 0, z: 1 },
    orientationKnown: Boolean(rawNormal),
    socketResolved,
    reasons,
  };
}

type Candidate = { point: MotionPoint; distance: number; heading: number };

/** Every spot in front of the fitting a chair of this size could actually occupy, nearest first. */
function approachCandidates(
  target: TargetGeometry,
  geometry: WheelchairMotionGeometry,
  radius: number,
  currentPos: MotionPoint | null | undefined,
): Candidate[] {
  const lateralAxis: MotionPoint = { x: -target.normal.z, z: target.normal.x };
  const candidates: Candidate[] = [];
  for (let dist = radius + 0.1; dist <= 0.7; dist += 0.1) {
    for (let lateral = -0.3; lateral <= 0.3; lateral += 0.1) {
      const point = add(target.position, add(scale(target.normal, dist), scale(lateralAxis, lateral)));
      if (!canOccupyWheelchair(point, geometry, radius)) continue;
      const toOutlet = subtract(target.position, point);
      candidates.push({
        point,
        distance: currentPos ? length(subtract(currentPos, point)) : 0,
        heading: (Math.atan2(toOutlet.x, toOutlet.z) * 180) / Math.PI,
      });
    }
  }
  return candidates.sort((a, b) => a.distance - b.distance);
}

/** Whether anything stands between these two points, the fitting itself excepted. */
function blockedBetween(
  from: MotionPoint,
  to: MotionPoint,
  outletNode: SceneNode,
  geometry: WheelchairMotionGeometry,
): boolean {
  return geometry.obstacles.some(
    (obs) => obs.node.id !== outletNode.id && segmentIntersectsRect(from, to, obs),
  );
}

type Approach = {
  status: ApproachStatus;
  candidate: MotionPoint | null;
  distance: number | null;
  heading: number | null;
  reasons: string[];
};

/** The nearest reachable spot the chair can both drive to and see the fitting from. */
function chooseApproach(
  currentPos: MotionPoint | null | undefined,
  candidates: Candidate[],
  target: TargetGeometry,
  outletNode: SceneNode,
  geometry: WheelchairMotionGeometry,
  radius: number,
): Approach {
  const nowhere: Approach = {
    status: "needs_verification",
    candidate: null,
    distance: null,
    heading: null,
    reasons: [],
  };
  if (!currentPos) return nowhere;

  for (const candidate of candidates) {
    const route = findWheelchairPath(currentPos, candidate.point, geometry, radius);
    if (!route.reached) continue;
    if (blockedBetween(candidate.point, target.position, outletNode, geometry)) continue;
    return {
      status: "clear",
      candidate: candidate.point,
      distance: route.distance,
      heading: candidate.heading,
      reasons: [],
    };
  }

  if (candidates.length === 0) {
    return {
      ...nowhere,
      status: "blocked",
      reasons: ["No valid modeled floor position found within approach range."],
    };
  }
  return {
    status: "blocked",
    candidate: candidates[0].point,
    distance: candidates[0].distance,
    heading: candidates[0].heading,
    reasons: [
      "Candidate stopping position exists on floor, but route from current position is obstructed.",
    ],
  };
}

type ValidatedReach = {
  maxDistance: number;
  minHeight: number;
  maxHeight: number;
  distanceSpan: [number, number];
  heightSpan: [number, number];
};

/** Which part of the reach profile the owner never supplied. */
function missingFromProfile(reach: NonNullable<WheelchairProfile["reach"]>): string | null {
  if (reach.maxReachDistance === undefined) {
    return "Maximum reach distance not supplied; reach cannot be established.";
  }
  if (reach.minReachHeight === undefined || reach.maxReachHeight === undefined) {
    return "Vertical reach limits (minReachHeight, maxReachHeight) not supplied; implicit ADA dimensions not assumed.";
  }
  return null;
}

/** Which part of the reach profile contradicts itself. */
function invalidInProfile(distance: number, low: number, high: number): string | null {
  if (!Number.isFinite(distance) || distance <= 0) {
    return "Invalid reach profile: maxReachDistance must be a finite positive number.";
  }
  if (!Number.isFinite(low) || !Number.isFinite(high) || low < 0 || low >= high) {
    return "Invalid reach profile: vertical limits must be finite numbers with minReachHeight < maxReachHeight.";
  }
  return null;
}

/** The profile's numbers once they are known to be usable, or the reason they are not. */
function validatedReach(
  profile: WheelchairProfile,
  reachDistance: number,
  heightAboveFloor: number,
): { problem: string } | { reach: ValidatedReach } {
  const reach = profile.reach;
  if (!reach) return { problem: "Personalized reach profile not supplied; reach cannot be established." };

  const absent = missingFromProfile(reach);
  if (absent) return { problem: absent };

  const maxDistance = reach.maxReachDistance!;
  const minHeight = reach.minReachHeight!;
  const maxHeight = reach.maxReachHeight!;
  const contradictory = invalidInProfile(maxDistance, minHeight, maxHeight);
  if (contradictory) return { problem: contradictory };

  return {
    reach: {
      maxDistance,
      minHeight,
      maxHeight,
      distanceSpan: reach.distanceInterval ?? [reachDistance, reachDistance],
      heightSpan: reach.heightInterval ?? [heightAboveFloor, heightAboveFloor],
    },
  };
}

type Verdict = { status: ReachStatus; reason: string | null };

const REACHED: Verdict = { status: "within_reach", reason: null };

/** Whether the fitting is near enough, refusing when the estimate straddles the limit. */
function distanceVerdict(reach: ValidatedReach, reachDistance: number): Verdict | null {
  const [nearest, furthest] = reach.distanceSpan;
  if (nearest <= reach.maxDistance && furthest > reach.maxDistance) {
    return {
      status: "needs_verification",
      reason: "Reach distance interval crosses maximum reach threshold; needs in-person verification.",
    };
  }
  if (nearest > reach.maxDistance) {
    return {
      status: "outside_reach",
      reason: `Estimated reach distance (${reachDistance.toFixed(2)}m) exceeds maximum modeled reach (${reach.maxDistance.toFixed(2)}m).`,
    };
  }
  return null;
}

/** Whether the fitting sits inside the vertical envelope, refusing when the estimate straddles it. */
function heightVerdict(reach: ValidatedReach, heightAboveFloor: number): Verdict | null {
  const [lowest, highest] = reach.heightSpan;
  const straddlesFloorLimit = lowest < reach.minHeight && highest >= reach.minHeight;
  const straddlesCeilingLimit = lowest <= reach.maxHeight && highest > reach.maxHeight;
  if (straddlesFloorLimit || straddlesCeilingLimit) {
    return {
      status: "needs_verification",
      reason: "Target height interval crosses vertical reach threshold; needs in-person verification.",
    };
  }
  if (heightAboveFloor < reach.minHeight || heightAboveFloor > reach.maxHeight) {
    return {
      status: "outside_reach",
      reason: `Target height (${heightAboveFloor.toFixed(2)}m) is outside vertical reach envelope (${reach.minHeight.toFixed(2)}m - ${reach.maxHeight.toFixed(2)}m).`,
    };
  }
  return null;
}

export function assessOutletAccessibility(
  currentPos: MotionPoint | null | undefined,
  outletNode: SceneNode,
  geometry: WheelchairMotionGeometry,
  profile: WheelchairProfile,
): OutletAccessibilityAssessment {
  const target = outletGeometry(outletNode, geometry);
  const unresolvedReasons = [...target.reasons];
  if (!currentPos) {
    unresolvedReasons.unshift("Current wheelchair position is unknown; route cannot be evaluated.");
  }

  const radius = profile.collisionRadius;
  const candidates = approachCandidates(target, geometry, radius, currentPos);
  const approach = chooseApproach(currentPos, candidates, target, outletNode, geometry, radius);
  unresolvedReasons.push(...approach.reasons);

  const reachFrom = approach.status === "clear" && approach.candidate ? approach.candidate : currentPos;
  const reachDistance = reachFrom ? length(subtract(reachFrom, target.position)) : null;

  const reach = evaluateReach(
    profile,
    target,
    approach,
    currentPos,
    reachDistance,
    outletNode,
    geometry,
  );
  unresolvedReasons.push(...reach.reasons);

  return {
    approachStatus: approach.status,
    approachCandidate: approach.candidate,
    approachDistance: approach.distance,
    approachHeadingDeg: approach.heading,
    reachStatus: reach.status,
    targetHeightAboveFloor: target.heightAboveFloor,
    reachDistance,
    unresolvedReasons,
    disclaimers: OUTLET_DISCLAIMERS,
  };
}

/** The fitting held against the owner's own numbers, once both are known to be usable. */
function measuredAgainstProfile(
  profile: WheelchairProfile,
  reachDistance: number,
  heightAboveFloor: number,
): { status: ReachStatus; reasons: string[] } {
  const checked = validatedReach(profile, reachDistance, heightAboveFloor);
  if ("problem" in checked) return { status: "needs_verification", reasons: [checked.problem] };
  const verdict =
    distanceVerdict(checked.reach, reachDistance) ??
    heightVerdict(checked.reach, heightAboveFloor) ??
    REACHED;
  return { status: verdict.status, reasons: verdict.reason ? [verdict.reason] : [] };
}

/** Everything that stops reach being answerable at all, before any measuring. */
function reachUnanswerable(
  target: TargetGeometry,
  reachDistance: number | null,
): { status: ReachStatus; reasons: string[] } | null {
  if (target.heightAboveFloor === null) {
    return {
      status: "needs_verification",
      reasons: ["Target height above floor is unknown; reach cannot be established."],
    };
  }
  if (!target.orientationKnown || !target.socketResolved || reachDistance === null) {
    return { status: "needs_verification", reasons: [] };
  }
  return null;
}

/** Whether the fitting can be reached from where the chair would stop, and why not when it cannot. */
function evaluateReach(
  profile: WheelchairProfile,
  target: TargetGeometry,
  approach: Approach,
  currentPos: MotionPoint | null | undefined,
  reachDistance: number | null,
  outletNode: SceneNode,
  geometry: WheelchairMotionGeometry,
): { status: ReachStatus; reasons: string[] } {
  const unanswerable = reachUnanswerable(target, reachDistance);
  if (unanswerable) return unanswerable;

  const from = approach.candidate ?? currentPos;
  if (from && blockedBetween(from, target.position, outletNode, geometry)) {
    return {
      status: "outside_reach",
      reasons: [
        "Reach path from stopping position to outlet is obstructed by an intervening obstacle.",
      ],
    };
  }

  return measuredAgainstProfile(profile, reachDistance!, target.heightAboveFloor!);
}
