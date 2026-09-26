import { dimensionAbove, dimensionLeft } from "../../../../../web/src/lib/schematic-brush/annotations";
import type { SchematicBrush } from "../../../../../web/src/lib/schematic-brush/brush";
import { boundsOf } from "../../../../../web/src/lib/schematic-brush/geometry";
import type { DraftRecorder } from "../../../../../web/src/lib/schematic-brush/recorder";
import { composeInk, type Point } from "../../../lib/ink";
import { closestShare, inches, onSheet, type SheetFrame } from "../../../lib/plan";
import type { FloorPlan, ScanObject } from "../../../lib/scan";

export const FAST_INK_ZOOM = 1.5;
const PEN_PX_PER_MS = 0.7;

type Drafting = { plan: FloorPlan; path: Point[]; frame: SheetFrame; walkMs: number };

const toInk = (frame: SheetFrame, point: Point): Point => {
  const [x, y] = onSheet(frame, point);
  return [x / FAST_INK_ZOOM, y / FAST_INK_ZOOM];
};

function lengthOf(points: Point[]) {
  return points.slice(1).reduce((sum, point, index) => sum + Math.hypot(point[0] - points[index][0], point[1] - points[index][1]), 0);
}

function dimensionAlongWidth(d: DraftRecorder, corners: Point[], label: string) {
  const [x0, y0, x1, y1] = boundsOf(corners);
  const [a, b] = corners;
  if (Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1])) dimensionAbove(d, [x0, y0], [x1, y0], y0 - d.unit * 1.2, label);
  else dimensionLeft(d, [x0, y0], [x0, y1], x0 - d.unit * 1.2, label);
}

function drawObject(d: DraftRecorder, frame: SheetFrame, object: ScanObject) {
  const corners = object.footprint.map((corner) => toInk(frame, corner));
  d.line([...corners, corners[0]], object.name === "table" ? "regular" : "thin");
  if (object.size[0] >= 1.5) dimensionAlongWidth(d, corners, inches(object.size[0]));
}

function draftRoom(brush: SchematicBrush, drafting: Drafting) {
  const { plan, frame, path, walkMs } = drafting;
  const passed = (point: Point) => closestShare(path, point) * walkMs;
  brush.stampWith((d) => d.line(path.map((point) => toInk(frame, point)), "regular"));
  plan.walls.forEach((wall) => brush.stampWith((d) => d.line([toInk(frame, wall[0]), toInk(frame, wall[1])], "heavy"), passed([(wall[0][0] + wall[1][0]) / 2, (wall[0][1] + wall[1][1]) / 2])));
  plan.objects.forEach((object) => brush.stampWith((d) => drawObject(d, frame, object), passed([object.center[0], object.center[2]])));
}

/** The walk as one continuous pen line, timed to take walkMs, with each wall and object inked as the pen passes it. No schematic nodes. */
export function composeFastSheet(drafting: Drafting) {
  const route = drafting.path.map((point) => toInk(drafting.frame, point));
  const speed = lengthOf(route) / (PEN_PX_PER_MS * drafting.walkMs);
  return composeInk({ seed: 3, unit: 15, speed }, (brush) => draftRoom(brush, drafting));
}
