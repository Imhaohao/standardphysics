import { dimensionAbove, dimensionLeft } from "../../../../web/src/lib/schematic-brush/annotations";
import type { SchematicBrush } from "../../../../web/src/lib/schematic-brush/brush";
import type { DraftRecorder } from "../../../../web/src/lib/schematic-brush/recorder";
import { boundsOf } from "../../../../web/src/lib/schematic-brush/geometry";
import { composeInk, type Point } from "../../lib/ink";
import { closestShare, inches, onSheet, type SheetFrame } from "../../lib/plan";
import type { FloorPlan, ScanObject } from "../../lib/scan";

export const INK_ZOOM = 1.5;

type Drafting = { plan: FloorPlan; path: Point[]; frame: SheetFrame; walkMs: number };

const toInk = (frame: SheetFrame, point: Point): Point => {
  const [x, y] = onSheet(frame, point);
  return [x / INK_ZOOM, y / INK_ZOOM];
};

function whenPassed({ path, walkMs }: Drafting, point: Point) {
  return closestShare(path, point) * walkMs;
}

function drawWall(d: DraftRecorder, frame: SheetFrame, [a, b]: [Point, Point]) {
  d.line([toInk(frame, a), toInk(frame, b)], "heavy");
}

function drawObject(d: DraftRecorder, frame: SheetFrame, object: ScanObject) {
  const corners = object.footprint.map((corner) => toInk(frame, corner));
  d.occupancy.claim(boundsOf(corners));
  d.line([...corners, corners[0]], object.name === "table" ? "regular" : "thin");
  if (object.size[0] >= 1.5) dimensionAlongWidth(d, corners, inches(object.size[0]));
}

/** Labels an object's measured width along whichever screen axis its long side runs. */
function dimensionAlongWidth(d: DraftRecorder, corners: Point[], label: string) {
  const [x0, y0, x1, y1] = boundsOf(corners);
  const [a, b] = corners;
  const runsAcross = Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1]);
  if (runsAcross) dimensionAbove(d, [x0, y0], [x1, y0], y0 - d.unit * 1.2, label);
  else dimensionLeft(d, [x0, y0], [x0, y1], x0 - d.unit * 1.2, label);
}

function draftRoom(brush: SchematicBrush, drafting: Drafting) {
  const { plan, frame } = drafting;
  plan.walls.forEach((wall) => brush.stampWith((d) => drawWall(d, frame, wall), whenPassed(drafting, [(wall[0][0] + wall[1][0]) / 2, (wall[0][1] + wall[1][1]) / 2])));
  plan.objects.forEach((object) => brush.stampWith((d) => drawObject(d, frame, object), whenPassed(drafting, [object.center[0], object.center[2]])));
  brush.draftRoute(
    drafting.path.map((point) => toInk(frame, point)),
    drafting.walkMs,
  );
}

/** The whole sheet as the pen will draw it: the walk itself, and each wall and object as the walker passes it. */
export function composeSheet(drafting: Drafting) {
  return composeInk({ seed: 3, unit: 15, speed: 1.1 }, (brush) => draftRoom(brush, drafting));
}
