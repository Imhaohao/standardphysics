"use client";

import { useMemo } from "react";
import { floorPolygon, footprint, type Point, type Polygon } from "@/lib/footprints";
import { doorKeepClear, swingsOpen } from "@/lib/layout-rules";
import { measuredPosition } from "@/lib/moves";
import { liesFlat } from "@/lib/room-shell";
import type { Stop } from "@/lib/slide";
import type { SceneGraph, SceneNode } from "@/types/contracts";
import { MAX_TRAVEL_METERS } from "@/types/geometry-rules";

/** The plan is drawn with y running down the screen, so room points flip on the way in. */
function drawn(polygon: Polygon): string {
  return polygon.map((point) => `${point.x.toFixed(4)},${(-point.y).toFixed(4)}`).join(" ");
}

const GUIDE = { stroke: "var(--color-accent)", vectorEffect: "non-scaling-stroke" as const };

function pressedNodes(pressedOn: Stop[], reason: Stop["reason"]): Set<string> {
  return new Set(pressedOn.filter((stop) => stop.reason === reason).map((stop) => stop.nodeId));
}

/**
 * The floor each door sweeps, shown while a piece is in hand so a piece that
 * stops in open floor in front of a door shows why. The square the piece is
 * pressed against is drawn solid.
 */
export function KeepClearSquares({ shown, pressedOn, hatch }: { shown: SceneGraph; pressedOn: Stop[]; hatch: string }) {
  const doors = useMemo(() => shown.nodes.filter(swingsOpen).map((door) => ({ id: door.id, zone: drawn(doorKeepClear(door)) })), [shown]);
  const pressed = pressedNodes(pressedOn, "blocked_a_door");
  return (
    <g aria-hidden className="pointer-events-none">
      {doors.map(({ id, zone }) => (
        <polygon
          key={id} points={zone} fill={hatch} fillOpacity={pressed.has(id) ? 1 : 0.6} {...GUIDE}
          strokeWidth={pressed.has(id) ? 2.5 : 1} strokeDasharray={pressed.has(id) ? undefined : "4 3"} strokeOpacity={pressed.has(id) ? 1 : 0.7}
        />
      ))}
    </g>
  );
}

function floorOutline(scanned: SceneGraph): string | null {
  const floor = scanned.nodes.find(liesFlat);
  return floor ? drawn(floorPolygon(floor)) : null;
}

function scannedSpot(scanned: SceneGraph, nodeId: string): Point | null {
  const node = scanned.nodes.find((candidate) => candidate.id === nodeId);
  return node ? measuredPosition(node) : null;
}

function Blocker({ node }: { node: SceneNode }) {
  return <polygon points={drawn(footprint(node))} fill="none" {...GUIDE} strokeWidth={2.5} />;
}

/**
 * What the piece in hand is pressed against: the piece or wall it touches, the
 * floor's edge, or the circle 60 inches round where the scan found it. The
 * door squares carry their own pressed state.
 */
export function PressedAgainst({ shown, scanned, pressedOn }: { shown: SceneGraph; scanned: SceneGraph; pressedOn: Stop[] }) {
  const touched = pressedNodes(pressedOn, "collided");
  const blockers = shown.nodes.filter((node) => touched.has(node.id));
  const edge = pressedOn.some((stop) => stop.reason === "left_the_floor") ? floorOutline(scanned) : null;
  const limits = pressedOn.filter((stop) => stop.reason === "moved_too_far")
    .map((stop) => scannedSpot(scanned, stop.nodeId))
    .filter((spot): spot is Point => spot !== null);
  return (
    <g aria-hidden className="pointer-events-none">
      {blockers.map((node) => <Blocker key={node.id} node={node} />)}
      {edge && <polygon points={edge} fill="none" {...GUIDE} strokeWidth={2.5} />}
      {limits.map((spot) => (
        <circle key={`${spot.x},${spot.y}`} cx={spot.x} cy={-spot.y} r={MAX_TRAVEL_METERS} fill="none" {...GUIDE} strokeWidth={1.5} strokeDasharray="6 4" />
      ))}
    </g>
  );
}
