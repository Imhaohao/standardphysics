import type { SchematicBrush } from "@/lib/brush/brush";
import { boxAround, type Point } from "@/lib/brush/geometry";
import type { DraftRecorder } from "@/lib/brush/recorder";
import type { FindingStatus } from "@/lib/findings/types";
import type { Vec2 } from "@/lib/scene/types";
import { shelfRows, type PlanAnnotations } from "./annotations";
import { dimensionAbove, dimensionLeft, draftFindingPin, leaderNoteAt, type ToFrame } from "./draft";

const DIMENSION_OFFSET_PX = 34;
const SHELF_OFFSET_PX = 30;
const NOTE_SPACING_PX = 34;
const NOTES_MIN_WIDTH_PX = 560;
const PIN_REACH_UNITS = 3.4;
const PIN_ANGLES = [-0.25, -0.75, 0.25, 0.75, -0.5, 0.5, 0, 1].map((turn) => turn * Math.PI);

export interface PlanPin {
  id: string;
  label: string;
  at: Vec2;
  status: FindingStatus;
}

/** Overall dimensions along the top and left of the plan, then size notes on shelves to its right. */
export function draftPlanAnnotations(brush: SchematicBrush, annotations: PlanAnnotations, toFrame: ToFrame, frameWidth: number, withNotes: boolean) {
  const { minX, minY, maxX, maxY } = annotations.bounds;
  const topLeft = toFrame({ x: minX, y: minY });
  const topRight = toFrame({ x: maxX, y: minY });
  const bottomLeft = toFrame({ x: minX, y: maxY });
  brush.stampWith((d) => dimensionAbove(d, topLeft, topRight, topLeft[1] - DIMENSION_OFFSET_PX, annotations.widthLabel));
  brush.stampWith((d) => dimensionLeft(d, topLeft, bottomLeft, topLeft[0] - DIMENSION_OFFSET_PX, annotations.depthLabel), 500);
  if (!withNotes || frameWidth < NOTES_MIN_WIDTH_PX) return;
  const targets = annotations.notes.map((note) => toFrame(note.at));
  const rows = shelfRows(targets.map((target) => target[1]), topRight[1], bottomLeft[1], NOTE_SPACING_PX);
  targets.forEach((target, index) => {
    const shelf: Point = [topRight[0] + SHELF_OFFSET_PX, rows[index]!];
    brush.stampWith((d) => leaderNoteAt(d, target, shelf, annotations.notes[index]!.text), 1000 + index * 350);
  });
}

function freeBubbleSpot(d: DraftRecorder, target: Point, bounds: readonly [number, number]): Point {
  const radius = d.unit * 1.5;
  const reach = d.unit * PIN_REACH_UNITS;
  const spots = PIN_ANGLES.map((angle): Point => [target[0] + Math.cos(angle) * reach, target[1] + Math.sin(angle) * reach]);
  const inside = (spot: Point) => spot[0] > radius && spot[1] > radius && spot[0] < bounds[0] - radius && spot[1] < bounds[1] - radius;
  const free = spots.find((spot) => inside(spot) && d.occupancy.isFree(boxAround(spot[0], spot[1], radius)));
  const chosen = free ?? spots.find(inside) ?? spots[0]!;
  d.occupancy.claim(boxAround(chosen[0], chosen[1], radius));
  return chosen;
}

/** Inks a numbered callout for each pin and returns where each bubble landed, in frame pixels. */
export function draftPins(brush: SchematicBrush, pins: readonly PlanPin[], toFrame: ToFrame, frameSize: readonly [number, number], colors: Record<FindingStatus, string>, startDelayMs = 1400) {
  const spots = new Map<string, Point>();
  pins.forEach((pin, index) => {
    brush.stampWith((d) => {
      const target = toFrame(pin.at);
      const bubble = freeBubbleSpot(d, target, frameSize);
      spots.set(pin.id, bubble);
      draftFindingPin(d, target, bubble, { color: colors[pin.status], label: pin.label });
    }, startDelayMs + index * 280);
  });
  return spots;
}
