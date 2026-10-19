import { roomCentroid, wallSegments, openingSpan } from "./plan";
import type { Room, Scene, Wall } from "./types";

/** A box to draw in 3D: centre, size (width along its local x, height, depth) and turn about Y. */
export interface ModelBox {
  id: string;
  center: [number, number, number];
  size: [number, number, number];
  rotationY: number;
}

const MIN_WALL_THICKNESS = 0.1;

function wallAngle(wall: Wall) {
  return -Math.atan2(wall.end.y - wall.start.y, wall.end.x - wall.start.x);
}

function wallPieces(room: Room, wall: Wall): ModelBox[] {
  const thickness = Math.max(wall.thickness, MIN_WALL_THICKNESS);
  const solid = wallSegments(wall, room.openings).map(([from, to], index): ModelBox => ({
    id: `${wall.id}:${index}`,
    center: [(from.x + to.x) / 2, wall.height / 2, (from.y + to.y) / 2],
    size: [Math.hypot(to.x - from.x, to.y - from.y), wall.height, thickness],
    rotationY: wallAngle(wall),
  }));
  const lintels = room.openings
    .filter((opening) => opening.wall_id === wall.id && opening.kind !== "window" && opening.width > 0.1)
    .map((opening): ModelBox | null => {
      const top = opening.center.y + opening.height / 2;
      if (top >= wall.height - 0.02) return null;
      const [from, to] = openingSpan(opening, wall);
      const length = Math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y) || 1;
      const middle = (from + to) / 2 / length;
      const x = wall.start.x + (wall.end.x - wall.start.x) * middle;
      const z = wall.start.y + (wall.end.y - wall.start.y) * middle;
      return { id: `${opening.id}:lintel`, center: [x, (top + wall.height) / 2, z], size: [to - from, wall.height - top, thickness], rotationY: wallAngle(wall) };
    })
    .filter((box): box is ModelBox => box !== null);
  return [...solid, ...lintels];
}

export function wallBoxes(scene: Scene): ModelBox[] {
  return scene.rooms.flatMap((room) => room.walls.flatMap((wall) => wallPieces(room, wall)));
}

export function objectBoxes(scene: Scene): ModelBox[] {
  return scene.rooms.flatMap((room) =>
    room.objects.map((object) => ({
      id: object.id,
      center: [object.center.x, object.center.y, object.center.z],
      size: [object.size.x, object.size.y, object.size.z],
      rotationY: object.yaw,
    })),
  );
}

/** Where the camera looks and how far back it stands to take in the whole scene. */
export function modelFraming(scene: Scene) {
  const points = scene.rooms.flatMap((room) => room.floor.points);
  if (points.length === 0) return { target: [0, 0, 0] as const, radius: 5 };
  const centre = roomCentroid({ ...scene.rooms[0]!, floor: { points } });
  const radius = Math.max(...points.map((p) => Math.hypot(p.x - centre.x, p.y - centre.y)), 2);
  return { target: [centre.x, 0.8, centre.y] as const, radius };
}
