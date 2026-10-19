import { arcPoints, HALF_PI, type Point } from "@/lib/brush/geometry";
import type { DraftRecorder } from "@/lib/brush/recorder";
import { objectCorners, openingEnds, wallNormal, wallSegments } from "@/lib/scene/plan";
import type { Opening, SceneObject, Vec2, Wall } from "@/lib/scene/types";

export type ToFrame = (point: Vec2) => Point;

const HATCH_SPACING_PX = 7;

export function dimensionAbove(d: DraftRecorder, left: Point, right: Point, lineY: number, label: string) {
  const tick = d.unit * 0.22;
  for (const end of [left, right]) d.line([[end[0], end[1] - d.unit * 0.4], [end[0], lineY - d.unit * 0.5]], "thin");
  d.line([[left[0], lineY], [right[0], lineY]], "thin");
  for (const end of [left, right]) d.line([[end[0] - tick, lineY + tick], [end[0] + tick, lineY - tick]], "regular");
  d.textAt(label, (left[0] + right[0]) / 2, lineY - d.unit * 0.25, d.fontSize(0.72), { align: "center", baseline: "bottom" });
}

export function dimensionLeft(d: DraftRecorder, top: Point, bottom: Point, lineX: number, label: string) {
  const tick = d.unit * 0.22;
  for (const end of [top, bottom]) d.line([[end[0] - d.unit * 0.4, end[1]], [lineX - d.unit * 0.5, end[1]]], "thin");
  d.line([[lineX, top[1]], [lineX, bottom[1]]], "thin");
  for (const end of [top, bottom]) d.line([[lineX - tick, end[1] + tick], [lineX + tick, end[1] - tick]], "regular");
  d.textAt(label, lineX - d.unit * 0.25, (top[1] + bottom[1]) / 2, d.fontSize(0.72), { align: "center", baseline: "bottom", rotation: -HALF_PI });
}

export function leaderNoteAt(d: DraftRecorder, target: Point, shelf: Point, text: string, color?: string) {
  const size = d.fontSize(0.66);
  const direction = shelf[0] >= target[0] ? 1 : -1;
  const shelfEnd: Point = [shelf[0] + direction * (d.measure(text, size) + d.unit * 0.4), shelf[1]];
  d.dot(target[0], target[1], d.unit * 0.16, color);
  d.line([target, shelf, shelfEnd], "thin", { color });
  d.textAt(text, shelf[0] + direction * d.unit * 0.2, shelf[1] - d.unit * 0.15, size, { align: direction > 0 ? "left" : "right", baseline: "bottom" });
}

export function draftWall(d: DraftRecorder, wall: Wall, openings: readonly Opening[], toFrame: ToFrame) {
  for (const [from, to] of wallSegments(wall, openings)) d.line([toFrame(from), toFrame(to)], "heavy");
}

/** A door draws its leaf standing open at 90 degrees and the arc its edge sweeps; a doorway draws its two jambs. */
export function draftOpening(d: DraftRecorder, opening: Opening, wall: Wall, inside: Vec2, toFrame: ToFrame) {
  if (opening.width <= 0.1 || opening.kind === "window") return;
  const [hinge, latch] = openingEnds(opening, wall).map(toFrame) as [Point, Point];
  const normal = wallNormal(wall, inside);
  const jamb = d.unit * 0.6;
  const cut = d.unit * 0.7;
  d.erase([
    [hinge[0] - normal.x * cut, hinge[1] - normal.y * cut],
    [latch[0] - normal.x * cut, latch[1] - normal.y * cut],
    [latch[0] + normal.x * cut, latch[1] + normal.y * cut],
    [hinge[0] + normal.x * cut, hinge[1] + normal.y * cut],
  ]);
  if (opening.kind === "opening") {
    for (const end of [hinge, latch]) d.line([[end[0] - normal.x * jamb, end[1] - normal.y * jamb], [end[0] + normal.x * jamb, end[1] + normal.y * jamb]], "regular");
    return;
  }
  const leaf = Math.hypot(latch[0] - hinge[0], latch[1] - hinge[1]);
  const closed = Math.atan2(latch[1] - hinge[1], latch[0] - hinge[0]);
  const open = Math.atan2(normal.y, normal.x);
  const sweep = Math.atan2(Math.sin(open - closed), Math.cos(open - closed));
  d.line([hinge, [hinge[0] + normal.x * leaf, hinge[1] + normal.y * leaf]], "regular");
  d.line(arcPoints(hinge[0], hinge[1], leaf, closed, closed + sweep), "thin");
}

function intersectX(a: Point, b: Point, offset: number): Point | null {
  const [sa, sb] = [a[0] + a[1] - offset, b[0] + b[1] - offset];
  if ((sa > 0 && sb > 0) || (sa < 0 && sb < 0) || sa === sb) return null;
  const t = sa / (sa - sb);
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** Clips the 45-degree line x + y = offset to a convex outline. */
function hatchChord(outline: readonly Point[], offset: number): [Point, Point] | null {
  const hits = outline.map((point, index) => intersectX(point, outline[(index + 1) % outline.length]!, offset)).filter((hit): hit is Point => hit !== null);
  return hits.length >= 2 ? [hits[0]!, hits[1]!] : null;
}

export function draftObject(d: DraftRecorder, object: SceneObject, toFrame: ToFrame) {
  const outline = objectCorners(object).map(toFrame);
  d.line([...outline, outline[0]!], "regular", { fill: true });
  const sums = outline.map(([x, y]) => x + y);
  for (let offset = Math.min(...sums) + HATCH_SPACING_PX; offset < Math.max(...sums); offset += HATCH_SPACING_PX * 1.4) {
    const chord = hatchChord(outline, offset);
    if (chord) d.line(chord, "thin");
  }
}

export interface PinStyle {
  color: string;
  label: string;
}

/** A numbered callout bubble tied back to the element a finding is about. */
export function draftFindingPin(d: DraftRecorder, target: Point, bubble: Point, style: PinStyle) {
  const radius = d.unit * 1.1;
  const angle = Math.atan2(target[1] - bubble[1], target[0] - bubble[0]);
  d.dot(target[0], target[1], d.unit * 0.2, style.color);
  d.line([target, [bubble[0] + Math.cos(angle) * radius, bubble[1] + Math.sin(angle) * radius]], "thin", { color: style.color });
  d.circle(bubble[0], bubble[1], radius, "regular", { fill: true, color: style.color });
  d.textAt(style.label, bubble[0], bubble[1], d.fontSize(0.72), { align: "center", baseline: "middle" });
}
