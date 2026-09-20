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
export function findWheelchairPath(
  start: MotionPoint,
  goal: MotionPoint,
  geometry: WheelchairMotionGeometry,
  radius: number,
  maxExpansions = 50000,
): { path: MotionPoint[]; reached: boolean; distance: number | null } {
  // 1. Direct line test (fast path)
  const direct = sweepWheelchairInGeometry(start, subtract(goal, start), geometry, radius);
  if (direct.reached) {
    return {
      path: [start, goal],
      reached: true,
      distance: length(subtract(goal, start)),
    };
  }

  // 2. A* grid search on measured floor
  const step = 0.10;
  const toKey = (p: MotionPoint) => `${Math.round(p.x / step)},${Math.round(p.z / step)}`;
  const startKey = toKey(start);

  type PathNode = {
    point: MotionPoint;
    g: number;
    f: number;
    parent: PathNode | null;
  };

  const openList: PathNode[] = [];
  const gScores = new Map<string, number>();
  const closedSet = new Set<string>();

  openList.push({
    point: start,
    g: 0,
    f: length(subtract(goal, start)),
    parent: null,
  });
  gScores.set(startKey, 0);

  let expansions = 0;
  const dirs = [
    { x: step, z: 0, cost: step },
    { x: -step, z: 0, cost: step },
    { x: 0, z: step, cost: step },
    { x: 0, z: -step, cost: step },
    { x: step, z: step, cost: step * Math.SQRT2 },
    { x: step, z: -step, cost: step * Math.SQRT2 },
    { x: -step, z: step, cost: step * Math.SQRT2 },
    { x: -step, z: -step, cost: step * Math.SQRT2 },
  ];

  while (openList.length > 0 && expansions < maxExpansions) {
    let bestIdx = 0;
    for (let i = 1; i < openList.length; i++) {
      if (openList[i].f < openList[bestIdx].f) {
        bestIdx = i;
      }
    }
    const current = openList.splice(bestIdx, 1)[0];
    const currKey = toKey(current.point);

    if (closedSet.has(currKey)) continue;
    closedSet.add(currKey);
    expansions++;

    // Check if within reach of goal
    const distToGoal = length(subtract(goal, current.point));
    if (distToGoal <= step * 2.0) {
      const finishSweep = sweepWheelchairInGeometry(current.point, subtract(goal, current.point), geometry, radius);
      if (finishSweep.reached) {
        const path: MotionPoint[] = [goal];
        let curr: PathNode | null = current;
        while (curr) {
          path.unshift(curr.point);
          curr = curr.parent;
        }
        let totalDist = 0;
        for (let i = 0; i < path.length - 1; i++) {
          totalDist += length(subtract(path[i + 1], path[i]));
        }
        return { path, reached: true, distance: totalDist };
      }
    }

    for (const dir of dirs) {
      const neighborPt: MotionPoint = {
        x: current.point.x + dir.x,
        z: current.point.z + dir.z,
      };
      const neighborKey = toKey(neighborPt);
      if (closedSet.has(neighborKey)) continue;

      if (!canOccupyWheelchair(neighborPt, geometry, radius)) continue;
      const stepSweep = sweepWheelchairInGeometry(current.point, subtract(neighborPt, current.point), geometry, radius);
      if (!stepSweep.reached) continue;

      const tentativeG = current.g + dir.cost;
      const existingG = gScores.get(neighborKey);
      if (existingG !== undefined && tentativeG >= existingG) continue;

      gScores.set(neighborKey, tentativeG);
      const h = length(subtract(goal, neighborPt));
      openList.push({
        point: neighborPt,
        g: tentativeG,
        f: tentativeG + h,
        parent: current,
      });
    }
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

export function assessOutletAccessibility(
  currentPos: MotionPoint | null | undefined,
  outletNode: SceneNode,
  geometry: WheelchairMotionGeometry,
  profile: WheelchairProfile,
): OutletAccessibilityAssessment {
  const unresolvedReasons: string[] = [];
  const disclaimers = [
    "Electrical power, circuit live status, voltage, and socket condition are not established.",
    "Plug insertion force, dexterity, and grip requirements are not established.",
    "ADA compliance is not established.",
    "Passing modeled reach is not proof of grasp, plug insertion, arm motion, strength or safe independent use.",
  ];

  if (!currentPos) {
    unresolvedReasons.push("Current wheelchair position is unknown; route cannot be evaluated.");
  }

  const targetPos: MotionPoint = { x: outletNode.transform.m[3], z: -outletNode.transform.m[7] };
  const targetHeight = outletNode.transform.m[11];

  // Find local floor directly under or closest to the target
  let targetHeightAboveFloor: number | null = null;
  const matchingFloor = geometry.floors.find((f) => containsPoint(f, targetPos, 0.05));
  if (matchingFloor) {
    const floorTop = matchingFloor.node.transform.m[11];
    targetHeightAboveFloor = Math.max(0, targetHeight - floorTop);
  } else {
    unresolvedReasons.push("No modeled floor under target; local floor elevation unknown.");
  }

  // Normal in motion plane (+X right, +Z in Three.js)
  const rawNormal = outletNode.attachment?.normal;
  if (!rawNormal) {
    unresolvedReasons.push("Outlet support normal is missing; orientation unknown.");
  }
  const motionNormal = rawNormal ? normalize({ x: rawNormal.x, z: -rawNormal.y }, { x: 0, z: 1 }) : { x: 0, z: 1 };

  // Socket target verification
  if (outletNode.attachment?.uncertainty_reasons?.some((r) => r.toLowerCase().includes("unresolved socket"))) {
    unresolvedReasons.push("Socket target is unresolved; cannot confirm operable reach.");
  }

  // Discretized candidate stopping positions in front of the outlet
  const candidates: { point: MotionPoint; distance: number; heading: number }[] = [];
  const radius = profile.collisionRadius;
  const lateralAxis: MotionPoint = { x: -motionNormal.z, z: motionNormal.x };

  for (let dist = radius + 0.10; dist <= 0.70; dist += 0.10) {
    for (let lateral = -0.30; lateral <= 0.30; lateral += 0.10) {
      const pt = add(targetPos, add(scale(motionNormal, dist), scale(lateralAxis, lateral)));
      if (canOccupyWheelchair(pt, geometry, radius)) {
        const toOutlet = subtract(targetPos, pt);
        const headingDeg = (Math.atan2(toOutlet.x, toOutlet.z) * 180) / Math.PI;
        const initialDist = currentPos ? length(subtract(currentPos, pt)) : 0;
        candidates.push({ point: pt, distance: initialDist, heading: headingDeg });
      }
    }
  }

  candidates.sort((a, b) => a.distance - b.distance);

  let approachStatus: ApproachStatus = currentPos ? "blocked" : "needs_verification";
  let bestCandidate: MotionPoint | null = null;
  let bestDistance: number | null = null;
  let bestHeading: number | null = null;

  if (currentPos) {
    for (const cand of candidates) {
      const pathRes = findWheelchairPath(currentPos, cand.point, geometry, radius);
      if (pathRes.reached) {
        // Check reach obstruction between stopping point and outlet
        const obstructed = geometry.obstacles.some((obs) => {
          if (obs.node.id === outletNode.id) return false;
          return segmentIntersectsRect(cand.point, targetPos, obs);
        });
        if (!obstructed) {
          approachStatus = "clear";
          bestCandidate = cand.point;
          bestDistance = pathRes.distance;
          bestHeading = cand.heading;
          break;
        }
      }
    }

    if (approachStatus !== "clear" && candidates.length > 0) {
      approachStatus = "blocked";
      bestCandidate = candidates[0].point;
      bestDistance = candidates[0].distance;
      bestHeading = candidates[0].heading;
      unresolvedReasons.push("Candidate stopping position exists on floor, but route from current position is obstructed.");
    } else if (candidates.length === 0) {
      approachStatus = "blocked";
      unresolvedReasons.push("No valid modeled floor position found within approach range.");
    }
  }

  // Reach assessment
  let reachStatus: ReachStatus = "needs_verification";
  const reachFromPoint = approachStatus === "clear" && bestCandidate ? bestCandidate : currentPos;
  const reachDistance = reachFromPoint ? length(subtract(reachFromPoint, targetPos)) : null;

  if (!profile.reach) {
    reachStatus = "needs_verification";
    unresolvedReasons.push("Personalized reach profile not supplied; reach cannot be established.");
  } else if (profile.reach.maxReachDistance === undefined) {
    reachStatus = "needs_verification";
    unresolvedReasons.push("Maximum reach distance not supplied; reach cannot be established.");
  } else if (profile.reach.minReachHeight === undefined || profile.reach.maxReachHeight === undefined) {
    reachStatus = "needs_verification";
    unresolvedReasons.push("Vertical reach limits (minReachHeight, maxReachHeight) not supplied; implicit ADA dimensions not assumed.");
  } else if (!Number.isFinite(profile.reach.maxReachDistance) || profile.reach.maxReachDistance <= 0) {
    reachStatus = "needs_verification";
    unresolvedReasons.push("Invalid reach profile: maxReachDistance must be a finite positive number.");
  } else if (
    !Number.isFinite(profile.reach.minReachHeight) ||
    !Number.isFinite(profile.reach.maxReachHeight) ||
    profile.reach.minReachHeight < 0 ||
    profile.reach.minReachHeight >= profile.reach.maxReachHeight
  ) {
    reachStatus = "needs_verification";
    unresolvedReasons.push("Invalid reach profile: vertical limits must be finite numbers with minReachHeight < maxReachHeight.");
  } else if (targetHeightAboveFloor === null) {
    reachStatus = "needs_verification";
    unresolvedReasons.push("Target height above floor is unknown; reach cannot be established.");
  } else if (!rawNormal) {
    reachStatus = "needs_verification";
  } else if (outletNode.attachment?.uncertainty_reasons?.some((r) => r.toLowerCase().includes("unresolved socket"))) {
    reachStatus = "needs_verification";
  } else if (reachDistance === null) {
    reachStatus = "needs_verification";
  } else {
    // Check if reach line intersects any obstacle
    const reachFromPoint = bestCandidate ?? currentPos;
    const reachObstructed = reachFromPoint
      ? geometry.obstacles.some((obs) => {
          if (obs.node.id === outletNode.id) return false;
          return segmentIntersectsRect(reachFromPoint, targetPos, obs);
        })
      : false;

    if (reachObstructed) {
      reachStatus = "outside_reach";
      unresolvedReasons.push("Reach path from stopping position to outlet is obstructed by an intervening obstacle.");
    } else {
      const { maxReachDistance, minReachHeight, maxReachHeight, distanceInterval, heightInterval } = profile.reach;

      const dInterval = distanceInterval ?? [reachDistance, reachDistance];
      const hInterval = heightInterval ?? [targetHeightAboveFloor, targetHeightAboveFloor];

      if (dInterval[0] <= maxReachDistance && dInterval[1] > maxReachDistance) {
        reachStatus = "needs_verification";
        unresolvedReasons.push("Reach distance interval crosses maximum reach threshold; needs in-person verification.");
      } else if (dInterval[0] > maxReachDistance) {
        reachStatus = "outside_reach";
        unresolvedReasons.push(`Estimated reach distance (${reachDistance.toFixed(2)}m) exceeds maximum modeled reach (${maxReachDistance.toFixed(2)}m).`);
      } else if (
        (hInterval[0] < minReachHeight && hInterval[1] >= minReachHeight) ||
        (hInterval[0] <= maxReachHeight && hInterval[1] > maxReachHeight)
      ) {
        reachStatus = "needs_verification";
        unresolvedReasons.push("Target height interval crosses vertical reach threshold; needs in-person verification.");
      } else if (targetHeightAboveFloor < minReachHeight || targetHeightAboveFloor > maxReachHeight) {
        reachStatus = "outside_reach";
        unresolvedReasons.push(`Target height (${targetHeightAboveFloor.toFixed(2)}m) is outside vertical reach envelope (${minReachHeight.toFixed(2)}m - ${maxReachHeight.toFixed(2)}m).`);
      } else {
        reachStatus = "within_reach";
      }
    }
  }

  return {
    approachStatus,
    approachCandidate: bestCandidate,
    approachDistance: bestDistance,
    approachHeadingDeg: bestHeading,
    reachStatus,
    targetHeightAboveFloor,
    reachDistance,
    unresolvedReasons,
    disclaimers,
  };
}
