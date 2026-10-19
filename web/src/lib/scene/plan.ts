import type { Point } from "@/lib/brush/geometry";
import type { Opening, Room, Scene, SceneObject, Vec2, Wall } from "./types";

export interface PlanBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface FrameRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Maps plan metres (world x, world z) to frame pixels, uniformly scaled and centred. Screen down is +z. */
export interface PlanProjection {
  scale: number;
  toFrame(point: Vec2): Point;
}

export function objectCorners(object: SceneObject): Vec2[] {
  const [cos, sin] = [Math.cos(object.yaw), Math.sin(object.yaw)];
  const axisX = { x: cos, y: -sin };
  const axisZ = { x: sin, y: cos };
  const [halfW, halfD] = [object.size.x / 2, object.size.z / 2];
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sz]) => ({
    x: object.center.x + axisX.x * halfW * sx! + axisZ.x * halfD * sz!,
    y: object.center.z + axisX.y * halfW * sx! + axisZ.y * halfD * sz!,
  }));
}

function roomPoints(room: Room): Vec2[] {
  return [...room.floor.points, ...room.walls.flatMap((wall) => [wall.start, wall.end]), ...room.objects.flatMap(objectCorners)];
}

export function planBounds(scene: Scene): PlanBounds | null {
  const points = scene.rooms.flatMap(roomPoints);
  if (points.length === 0) return null;
  return {
    minX: Math.min(...points.map((p) => p.x)),
    minY: Math.min(...points.map((p) => p.y)),
    maxX: Math.max(...points.map((p) => p.x)),
    maxY: Math.max(...points.map((p) => p.y)),
  };
}

export function fitProjection(bounds: PlanBounds, frame: FrameRect): PlanProjection {
  const [width, depth] = [Math.max(bounds.maxX - bounds.minX, 0.5), Math.max(bounds.maxY - bounds.minY, 0.5)];
  const scale = Math.min(frame.width / width, frame.height / depth);
  const offsetX = frame.left + (frame.width - width * scale) / 2;
  const offsetY = frame.top + (frame.height - depth * scale) / 2;
  return { scale, toFrame: (point) => [offsetX + (point.x - bounds.minX) * scale, offsetY + (point.y - bounds.minY) * scale] };
}

/** Where along its wall an opening sits, as distances from the wall's start in metres. */
export function openingSpan(opening: Opening, wall: Wall): [number, number] {
  const [dx, dy] = [wall.end.x - wall.start.x, wall.end.y - wall.start.y];
  const length = Math.hypot(dx, dy) || 1;
  const along = ((opening.center.x - wall.start.x) * dx + (opening.center.z - wall.start.y) * dy) / length;
  return [Math.max(0, along - opening.width / 2), Math.min(length, along + opening.width / 2)];
}

function pointAlong(wall: Wall, distance: number): Vec2 {
  const length = Math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y) || 1;
  const t = distance / length;
  return { x: wall.start.x + (wall.end.x - wall.start.x) * t, y: wall.start.y + (wall.end.y - wall.start.y) * t };
}

/** The solid runs of a wall once its doors and doorways are cut out of it. */
export function wallSegments(wall: Wall, openings: readonly Opening[]): [Vec2, Vec2][] {
  const length = Math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y);
  const cuts = openings
    .filter((opening) => opening.wall_id === wall.id && opening.kind !== "window" && opening.width > 0.1)
    .map((opening) => openingSpan(opening, wall))
    .sort((a, b) => a[0] - b[0]);
  const segments: [Vec2, Vec2][] = [];
  let cursor = 0;
  for (const [from, to] of cuts) {
    if (from > cursor) segments.push([pointAlong(wall, cursor), pointAlong(wall, from)]);
    cursor = Math.max(cursor, to);
  }
  if (cursor < length) segments.push([pointAlong(wall, cursor), pointAlong(wall, length)]);
  return segments;
}

export function openingEnds(opening: Opening, wall: Wall): [Vec2, Vec2] {
  const [from, to] = openingSpan(opening, wall);
  return [pointAlong(wall, from), pointAlong(wall, to)];
}

/** A unit vector at right angles to the wall, pointing into the room (towards `inside`). */
export function wallNormal(wall: Wall, inside: Vec2): Vec2 {
  const [dx, dy] = [wall.end.x - wall.start.x, wall.end.y - wall.start.y];
  const length = Math.hypot(dx, dy) || 1;
  const normal = { x: -dy / length, y: dx / length };
  const towardInside = (inside.x - wall.start.x) * normal.x + (inside.y - wall.start.y) * normal.y;
  return towardInside >= 0 ? normal : { x: -normal.x, y: -normal.y };
}

export function roomCentroid(room: Room): Vec2 {
  const points = room.floor.points.length > 0 ? room.floor.points : room.walls.flatMap((wall) => [wall.start, wall.end]);
  const count = points.length || 1;
  return { x: points.reduce((sum, p) => sum + p.x, 0) / count, y: points.reduce((sum, p) => sum + p.y, 0) / count };
}

/** The angle (mod 90 degrees) most walls run at, weighted by length, so a plan can be turned square to the sheet. */
export function dominantWallAngle(scene: Scene) {
  let [sumCos, sumSin] = [0, 0];
  for (const wall of scene.rooms.flatMap((room) => room.walls)) {
    const [dx, dy] = [wall.end.x - wall.start.x, wall.end.y - wall.start.y];
    const [length, angle] = [Math.hypot(dx, dy), Math.atan2(dy, dx)];
    sumCos += length * Math.cos(4 * angle);
    sumSin += length * Math.sin(4 * angle);
  }
  return sumCos === 0 && sumSin === 0 ? 0 : Math.atan2(sumSin, sumCos) / 4;
}

export type PlanRotation = (point: Vec2) => Vec2;

export function rotationBy(angle: number): PlanRotation {
  const [cos, sin] = [Math.cos(angle), Math.sin(angle)];
  return ({ x, y }) => ({ x: x * cos - y * sin, y: x * sin + y * cos });
}

function rotateRoom(room: Room, rotate: PlanRotation, angle: number): Room {
  const rotate3 = <T extends { x: number; z: number }>(point: T): T => {
    const turned = rotate({ x: point.x, y: point.z });
    return { ...point, x: turned.x, z: turned.y };
  };
  return {
    ...room,
    floor: { points: room.floor.points.map(rotate) },
    walls: room.walls.map((wall) => ({ ...wall, start: rotate(wall.start), end: rotate(wall.end) })),
    openings: room.openings.map((opening) => ({ ...opening, center: rotate3(opening.center) })),
    objects: room.objects.map((object) => ({ ...object, center: rotate3(object.center), yaw: object.yaw - angle })),
  };
}

/** The scene turned so its walls run square to the sheet, and the rotation to apply to anything pinned on it. */
export function squaredToSheet(scene: Scene): { scene: Scene; rotate: PlanRotation } {
  const angle = -dominantWallAngle(scene);
  const rotate = rotationBy(angle);
  return { scene: { ...scene, rooms: scene.rooms.map((room) => rotateRoom(room, rotate, angle)) }, rotate };
}
