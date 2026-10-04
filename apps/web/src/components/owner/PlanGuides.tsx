"use client";

import { useId, useMemo } from "react";
import { floorPolygon, footprint, type Point, type Polygon } from "@/lib/footprints";
import { doorKeepClear, swingsOpen } from "@/lib/layout-rules";
import { measuredPosition } from "@/lib/moves";
import { liesFlat } from "@/lib/room-shell";
import type { Stop } from "@/lib/slide";
import type { SceneGraph } from "@/types/contracts";
import { MAX_TRAVEL_METERS } from "@/types/geometry-rules";

/** The plan is drawn with y running down the screen, so room points flip on the way in. */
function drawn(polygon: Polygon): string {
  return polygon.map((point) => `${point.x.toFixed(4)},${(-point.y).toFixed(4)}`).join(" ");
}

const ACCENT = { stroke: "var(--color-accent)", vectorEffect: "non-scaling-stroke" as const };

function pressedNodes(pressedOn: Stop[], reason: Stop["reason"]): Set<string> {
  return new Set(pressedOn.filter((stop) => stop.reason === reason).map((stop) => stop.nodeId));
}

function floorOutline(scene: SceneGraph): string | null {
  const floor = scene.nodes.find(liesFlat);
  return floor ? drawn(floorPolygon(floor)) : null;
}

/**
 * The outline of something the piece in hand is pressed against: a soft halo
 * with a thin line through it, so it reads as lit by the contact rather than
 * picked up like the piece itself.
 */
function Lit({ points }: { points: string }) {
  return (
    <>
      <polygon points={points} fill="none" {...ACCENT} strokeWidth={7} strokeOpacity={0.22} />
      <polygon points={points} fill="none" {...ACCENT} strokeWidth={1.5} />
    </>
  );
}

/**
 * The floor each door sweeps, shown while a piece is in hand so a piece that
 * stops in open floor in front of a door shows why. Only the part over the
 * floor is drawn, and the square the piece is pressed against is lit.
 */
export function KeepClearSquares({ shown, pressedOn, hatch }: { shown: SceneGraph; pressedOn: Stop[]; hatch: string }) {
  const clipId = useId();
  const floor = useMemo(() => floorOutline(shown), [shown]);
  const doors = useMemo(() => shown.nodes.filter(swingsOpen).map((door) => ({ id: door.id, zone: drawn(doorKeepClear(door)) })), [shown]);
  const pressed = pressedNodes(pressedOn, "blocked_a_door");
  return (
    <g aria-hidden className="pointer-events-none">
      {floor && <clipPath id={clipId}><polygon points={floor} /></clipPath>}
      <g clipPath={floor ? `url(#${clipId})` : undefined}>
        {doors.map(({ id, zone }) => (
          <g key={id}>
            <polygon points={zone} fill={hatch} {...ACCENT} strokeWidth={1.25} strokeDasharray={pressed.has(id) ? undefined : "5 3"} />
            {pressed.has(id) && <Lit points={zone} />}
          </g>
        ))}
      </g>
    </g>
  );
}

function scannedSpot(scanned: SceneGraph, nodeId: string): Point | null {
  const node = scanned.nodes.find((candidate) => candidate.id === nodeId);
  return node ? measuredPosition(node) : null;
}

/**
 * What the piece in hand is pressed against: the piece or wall it touches, the
 * floor's edge, or the circle 60 inches round where the scan found it. The
 * door squares light up on their own.
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
      {blockers.map((node) => <Lit key={node.id} points={drawn(footprint(node))} />)}
      {edge && <Lit points={edge} />}
      {limits.map((spot) => (
        <circle key={`${spot.x},${spot.y}`} cx={spot.x} cy={-spot.y} r={MAX_TRAVEL_METERS} fill="none" {...ACCENT} strokeWidth={1.5} strokeDasharray="6 4" />
      ))}
    </g>
  );
}
