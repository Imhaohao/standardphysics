import type { Opening, OpeningKind, Room, RoomKind, Scene, SceneObject, Vec2, Vec3, Wall } from "./types";

/**
 * Converts an Apple RoomPlan `CapturedRoom` JSON export into a v2 Scene, following the same conventions as
 * core's importer: plan = world (x, z), floor moved to y = 0, yaw measured from the object's local X axis.
 * The web app uses it only to build its bundled fixture.
 */
type Matrix = readonly number[];

interface RawSurface {
  identifier: string;
  parentIdentifier?: string | null;
  dimensions: number[];
  transform: Matrix;
  polygonCorners?: number[][];
  category?: Record<string, Record<string, unknown>>;
}

interface RawObject {
  identifier: string;
  dimensions: number[];
  transform: Matrix;
  category: Record<string, unknown>;
  attributes?: Record<string, unknown>;
  confidence?: Record<string, unknown>;
}

export interface CapturedRoom {
  identifier?: string;
  story?: number;
  walls?: RawSurface[];
  doors?: RawSurface[];
  windows?: RawSurface[];
  openings?: RawSurface[];
  floors?: RawSurface[];
  objects?: RawObject[];
  sections?: { label: string; center: number[] }[];
}

const DEFAULT_WALL_THICKNESS = 0.1;
const CONFIDENCE: Record<string, number> = { high: 1, medium: 0.66, low: 0.33 };
const ROOM_KINDS: Record<string, RoomKind> = {
  bathroom: "restroom",
  kitchen: "kitchen",
  diningRoom: "restaurant",
  hallway: "corridor",
  corridor: "corridor",
  office: "office",
  study: "office",
  storage: "storage",
  closet: "storage",
  laundryRoom: "storage",
};
const REFINED_CATEGORY: Record<string, Record<string, Record<string, string>>> = {
  table: { TableType: { coffee: "coffee_table", dining: "dining_table" } },
  storage: { StorageType: { shelf: "shelving", cabinet: "cabinet" } },
  chair: { ChairType: { stool: "stool" } },
};

function at(matrix: Matrix, index: number) {
  return matrix[index] ?? 0;
}

function translation(matrix: Matrix): Vec3 {
  return { x: at(matrix, 12), y: at(matrix, 13), z: at(matrix, 14) };
}

function apply(matrix: Matrix, [x = 0, y = 0, z = 0]: number[]): Vec3 {
  return {
    x: at(matrix, 0) * x + at(matrix, 4) * y + at(matrix, 8) * z + at(matrix, 12),
    y: at(matrix, 1) * x + at(matrix, 5) * y + at(matrix, 9) * z + at(matrix, 13),
    z: at(matrix, 2) * x + at(matrix, 6) * y + at(matrix, 10) * z + at(matrix, 14),
  };
}

export function yawOf(matrix: Matrix) {
  return Math.atan2(-at(matrix, 2), at(matrix, 0));
}

function plan(point: Vec3): Vec2 {
  return { x: point.x, y: point.z };
}

export function snakeCase(camel: string) {
  return camel.replace(/(?!^)([A-Z])/g, "_$1").toLowerCase();
}

function humanize(label: string) {
  const words = snakeCase(label).replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function enumCase(category: Record<string, unknown>) {
  return Object.keys(category)[0] ?? "unknown";
}

export function floorLevel(raw: CapturedRoom) {
  const floors = (raw.floors ?? []).map((floor) => translation(floor.transform).y);
  const walls = (raw.walls ?? []).map((wall) => translation(wall.transform).y - (wall.dimensions[1] ?? 0) / 2);
  const objects = (raw.objects ?? []).map((object) => translation(object.transform).y - (object.dimensions[1] ?? 0) / 2);
  const lowest = [floors, walls, objects].map((levels) => Math.min(...levels)).find(Number.isFinite);
  return lowest ?? 0;
}

function wallEndpoints(wall: RawSurface): [Vec2, Vec2] {
  const center = plan(translation(wall.transform));
  const axisLength = Math.hypot(at(wall.transform, 0), at(wall.transform, 2)) || 1;
  const half = (wall.dimensions[0] ?? 0) / 2 / axisLength;
  const [dx, dz] = [at(wall.transform, 0) * half, at(wall.transform, 2) * half];
  return [
    { x: center.x - dx, y: center.y - dz },
    { x: center.x + dx, y: center.y + dz },
  ];
}

function convertWall(wall: RawSurface, level: number): Wall {
  const [start, end] = wallEndpoints(wall);
  const height = wall.dimensions[1] ?? 0;
  const top = translation(wall.transform).y + height / 2 - level;
  const thickness = wall.dimensions[2] ?? 0;
  return { id: wall.identifier, start, end, height: Math.max(top, height), thickness: thickness > 0 ? thickness : DEFAULT_WALL_THICKNESS };
}

function distanceToWall(point: Vec2, wall: Wall) {
  const [dx, dy] = [wall.end.x - wall.start.x, wall.end.y - wall.start.y];
  const lengthSquared = dx * dx + dy * dy || 1;
  const t = Math.min(1, Math.max(0, ((point.x - wall.start.x) * dx + (point.y - wall.start.y) * dy) / lengthSquared));
  return Math.hypot(point.x - (wall.start.x + t * dx), point.y - (wall.start.y + t * dy));
}

function hostWallId(surface: RawSurface, walls: Wall[], center: Vec2) {
  const parent = walls.find((wall) => wall.id === surface.parentIdentifier);
  if (parent) return parent.id;
  const nearest = [...walls].sort((a, b) => distanceToWall(center, a) - distanceToWall(center, b))[0];
  return nearest?.id ?? "";
}

function convertOpening(kind: OpeningKind, surface: RawSurface, walls: Wall[], level: number): Opening {
  const world = translation(surface.transform);
  const center = { x: world.x, y: world.y - level, z: world.z };
  const isOpen = surface.category?.door?.isOpen === true;
  return {
    id: surface.identifier,
    kind,
    wall_id: hostWallId(surface, walls, plan(center)),
    center,
    width: surface.dimensions[0] ?? 0,
    height: surface.dimensions[1] ?? 0,
    swing: null,
    hardware: isOpen ? "captured_open" : null,
  };
}

export function objectCategory(roomplanCase: string, attributes: Record<string, string>) {
  const refinements = REFINED_CATEGORY[roomplanCase] ?? {};
  for (const [attribute, values] of Object.entries(refinements)) {
    const refined = values[attributes[attribute] ?? ""];
    if (refined) return refined;
  }
  if (roomplanCase === "stove") return "range";
  return snakeCase(roomplanCase);
}

function convertObject(object: RawObject, level: number): SceneObject {
  const world = translation(object.transform);
  const [width = 0, height = 0, depth = 0] = object.dimensions;
  const center = { x: world.x, y: world.y - level, z: world.z };
  const roomplanCase = enumCase(object.category);
  const attributes = Object.fromEntries(Object.entries(object.attributes ?? {}).map(([key, value]) => [key, String(value)]));
  return {
    id: object.identifier,
    category: objectCategory(roomplanCase, attributes),
    center,
    size: { x: width, y: height, z: depth },
    yaw: yawOf(object.transform),
    top_height: center.y + height / 2,
    confidence: CONFIDENCE[enumCase(object.confidence ?? { high: {} })] ?? 1,
    source: "roomplan",
    attributes: { ...attributes, roomplan_category: roomplanCase },
  };
}

function polygonArea(points: Vec2[]) {
  return Math.abs(points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length]!;
    return sum + point.x * next.y - next.x * point.y;
  }, 0)) / 2;
}

function floorPolygon(floor: RawSurface): Vec2[] {
  const [width = 0, depth = 0] = floor.dimensions;
  const corners = (floor.polygonCorners?.length ?? 0) >= 3 ? floor.polygonCorners! : [[-width / 2, -depth / 2, 0], [width / 2, -depth / 2, 0], [width / 2, depth / 2, 0], [-width / 2, depth / 2, 0]];
  return corners.map((corner) => plan(apply(floor.transform, corner)));
}

function outlineFromWalls(walls: Wall[]): Vec2[] {
  const points = walls.flatMap((wall) => [wall.start, wall.end]);
  const mean = { x: points.reduce((s, p) => s + p.x, 0) / points.length, y: points.reduce((s, p) => s + p.y, 0) / points.length };
  const sorted = points.sort((a, b) => Math.atan2(a.y - mean.y, a.x - mean.x) - Math.atan2(b.y - mean.y, b.x - mean.x));
  return sorted.filter((point, index) => index === 0 || Math.hypot(point.x - sorted[index - 1]!.x, point.y - sorted[index - 1]!.y) >= 0.05);
}

function floorOutline(raw: CapturedRoom, walls: Wall[]): Vec2[] {
  const floors = (raw.floors ?? []).map(floorPolygon).filter((points) => points.length >= 3 && polygonArea(points) > 0);
  const largest = floors.sort((a, b) => polygonArea(b) - polygonArea(a))[0];
  return largest ?? outlineFromWalls(walls);
}

function roomIdentity(raw: CapturedRoom, index: number) {
  const section = raw.sections?.[0];
  return {
    id: raw.identifier ?? raw.floors?.[0]?.identifier ?? `room-${index}`,
    name: section ? humanize(section.label) : `Room ${index + 1}`,
    kind: (section ? ROOM_KINDS[section.label] : undefined) ?? "other",
    storey: raw.story ?? 0,
  };
}

function convertOpenings(raw: CapturedRoom, walls: Wall[], level: number) {
  const sources: [OpeningKind, RawSurface[] | undefined][] = [["door", raw.doors], ["opening", raw.openings], ["window", raw.windows]];
  return sources.flatMap(([kind, surfaces]) => (surfaces ?? []).map((surface) => convertOpening(kind, surface, walls, level)));
}

export function convertCapturedRoom(raw: CapturedRoom, index = 0): Room {
  const level = floorLevel(raw);
  const walls = (raw.walls ?? []).map((wall) => convertWall(wall, level));
  return {
    ...roomIdentity(raw, index),
    floor: { points: floorOutline(raw, walls) },
    ceiling_height: walls.reduce((highest, wall) => Math.max(highest, wall.height), 0) || 2.4,
    walls,
    openings: convertOpenings(raw, walls, level),
    objects: (raw.objects ?? []).map((object) => convertObject(object, level)),
  };
}

export function sceneFromCapturedRoom(raw: CapturedRoom): Scene {
  return { version: 2, rooms: [convertCapturedRoom(raw)], connections: [], observations: [] };
}
