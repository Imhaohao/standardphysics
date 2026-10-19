import { arcPoints } from "@/lib/brush/geometry";
import { objectCorners, openingEnds, planBounds, roomCentroid, wallNormal, wallSegments } from "@/lib/scene/plan";
import type { Opening, Room, Scene, Vec2, Wall } from "@/lib/scene/types";

const THINNEST_WALL_METRES = 0.1;

function pointsAttribute(points: readonly Vec2[]) {
  return points.map((point) => `${point.x.toFixed(3)},${point.y.toFixed(3)}`).join(" ");
}

function DoorSwing({ opening, wall, inside }: { opening: Opening; wall: Wall; inside: Vec2 }) {
  const [hinge, latch] = openingEnds(opening, wall);
  const normal = wallNormal(wall, inside);
  const leaf = Math.hypot(latch.x - hinge.x, latch.y - hinge.y);
  const closed = Math.atan2(latch.y - hinge.y, latch.x - hinge.x);
  const open = Math.atan2(normal.y, normal.x);
  const sweep = Math.atan2(Math.sin(open - closed), Math.cos(open - closed));
  const arc = arcPoints(hinge.x, hinge.y, leaf, closed, closed + sweep).map(([x, y]) => ({ x, y }));
  const leafEnd = { x: hinge.x + normal.x * leaf, y: hinge.y + normal.y * leaf };
  return (
    <g stroke="var(--color-ink)" fill="none" vectorEffect="non-scaling-stroke">
      <polyline points={pointsAttribute([hinge, leafEnd])} strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
      <polyline points={pointsAttribute(arc)} strokeWidth={0.75} vectorEffect="non-scaling-stroke" />
    </g>
  );
}

function RoomPlan({ room, hatchId }: { room: Room; hatchId: string }) {
  const inside = roomCentroid(room);
  const wallsById = new Map(room.walls.map((wall) => [wall.id, wall]));
  const doors = room.openings.filter((opening) => opening.kind === "door" && opening.width > 0.1);
  return (
    <g>
      <polygon points={pointsAttribute(room.floor.points)} fill="none" stroke="var(--color-ink-faint)" strokeWidth={0.75} vectorEffect="non-scaling-stroke" />
      {room.objects.map((object) => (
        <polygon key={object.id} points={pointsAttribute(objectCorners(object))} fill={`url(#${hatchId})`} stroke="var(--color-ink)" strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
      ))}
      {room.walls.flatMap((wall) =>
        wallSegments(wall, room.openings).map(([from, to], index) => (
          <line key={`${wall.id}-${index}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="var(--color-ink)" strokeWidth={Math.max(wall.thickness, THINNEST_WALL_METRES)} strokeLinecap="square" />
        )),
      )}
      {doors.map((door) => {
        const wall = wallsById.get(door.wall_id);
        return wall ? <DoorSwing key={door.id} opening={door} wall={wall} inside={inside} /> : null;
      })}
    </g>
  );
}

/** The shop from above, drawn from measured geometry: walls cut by their doors, furniture hatched. */
export function PlanSvg({ scene, name, className = "" }: { scene: Scene; name: string; className?: string }) {
  const bounds = planBounds(scene);
  if (!bounds) return null;
  const [width, depth] = [bounds.maxX - bounds.minX, bounds.maxY - bounds.minY];
  const pad = Math.max(width, depth) * 0.04;
  const hatchSpacing = Math.max(width, depth) / 90;
  const hatchId = `plan-hatch-${name}`;
  return (
    <svg viewBox={`${bounds.minX - pad} ${bounds.minY - pad} ${width + 2 * pad} ${depth + 2 * pad}`} className={className} aria-hidden data-floor-plan>
      <defs>
        <pattern id={hatchId} width={hatchSpacing} height={hatchSpacing} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width={hatchSpacing} height={hatchSpacing} fill="var(--color-paper)" />
          <line x1="0" y1="0" x2="0" y2={hatchSpacing} stroke="var(--color-ink)" strokeWidth={hatchSpacing * 0.18} />
        </pattern>
      </defs>
      {scene.rooms.map((room) => (
        <RoomPlan key={room.id} room={room} hatchId={hatchId} />
      ))}
    </svg>
  );
}
