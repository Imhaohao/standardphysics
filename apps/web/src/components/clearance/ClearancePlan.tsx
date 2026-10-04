"use client";

import { pinchesToMark, pinchWords, roomPointOf, type Segment } from "@/lib/clearance-map";
import { type PlanLabel, type PlanPoint, turnedPoint } from "@/lib/plan-view";
import type { ClearanceBands, ClearancePinch } from "@/types/contracts";
import type { ClearancePicture } from "./useClearancePicture";

/** The map as the plan and the model draw it, and whether it still shows a layout the owner has since moved on from. */
export type ClearanceOverlay = { picture: ClearancePicture; url: string | null; stale: boolean };

/** How faint the map goes while it catches up with a drag, so a map of the last layout never passes for this one. */
export const STALE_OPACITY = 0.4;

/** The pinch ring's radius, in plan text heights, so it reads the same size on screen whatever the room's size. */
const RING_TEXT_SHARE = 0.42;

function pathOf(segments: Segment[]): string {
  return segments.map(([a, b]) => `M${a.x.toFixed(3)} ${(-a.y).toFixed(3)}L${b.x.toFixed(3)} ${(-b.y).toFixed(3)}`).join("");
}

/**
 * The map under the furniture: the floor tinted by how wide the clear space is around each point, and a red line
 * where it gets too tight for a wheelchair. Drawn in room metres with y flipped, inside the plan's turned group.
 */
export function ClearancePlanField({ overlay }: { overlay: ClearanceOverlay }) {
  const { picture, url, stale } = overlay;
  const { field } = picture;
  const corner = roomPointOf(field, 0, 0);
  const tight = pathOf(picture.tightEdge);
  return (
    <g aria-hidden className="pointer-events-none transition-opacity duration-200 motion-reduce:transition-none" opacity={stale ? STALE_OPACITY : 1}>
      {url && (
        <image
          href={url} x={corner.x} y={-corner.y} width={field.columns * field.cellMeters} height={field.rows * field.cellMeters}
          preserveAspectRatio="none" transform={`rotate(${-field.rotationDegrees} ${corner.x} ${-corner.y})`}
        />
      )}
      <path d={tight} fill="none" stroke="var(--color-clearance-halo)" strokeWidth={4.5} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <path d={tight} fill="none" stroke="var(--color-clearance-tight)" strokeWidth={1.5} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </g>
  );
}

/** A ring on each gap the route cannot get through at its required width, drawn over the furniture beside it. */
export function ClearancePinchRings({ overlay, textMeters }: { overlay: ClearanceOverlay; textMeters: number }) {
  const radius = textMeters * RING_TEXT_SHARE;
  return (
    <g aria-hidden className="pointer-events-none" opacity={overlay.stale ? STALE_OPACITY : 1}>
      {pinchesToMark(overlay.picture.field).map((pinch) => (
        <g key={pinch.finding_id} transform={`translate(${pinch.point.x.toFixed(4)} ${(-pinch.point.y).toFixed(4)})`}>
          <circle r={radius * 1.9} fill="var(--color-clearance-tight)" fillOpacity={0.16} />
          <circle r={radius} fill="var(--color-sheet)" stroke="var(--color-clearance-tight)" strokeWidth={2.5} vectorEffect="non-scaling-stroke" />
          <circle r={radius * 0.32} fill="var(--color-clearance-tight)" />
        </g>
      ))}
    </g>
  );
}

const PINCH_LABEL = "pinch-";

/** Each marked pinch's width, upright above its ring, ready for the plan's own label placement. */
export function pinchLabels(pinches: ClearancePinch[], bands: ClearanceBands, turnDegrees: number, textMeters: number): PlanLabel[] {
  return pinches.map((pinch) => {
    const centre: PlanPoint = turnedPoint(pinch.point, turnDegrees);
    return { key: `${PINCH_LABEL}${pinch.finding_id}`, text: pinchWords(pinch, bands), x: centre.x, y: centre.y - textMeters * (RING_TEXT_SHARE * 1.9 + 0.3) };
  });
}

export function isPinchLabel(label: PlanLabel): boolean {
  return label.key.startsWith(PINCH_LABEL);
}
