import { arcPoints, boundsOf, boxAround, HALF_PI, QUARTER_PI, rectPoints, type Box, type Point } from "./geometry";
import { drawCalloutBubble, drawSectionMarker, type DraftNode } from "./nodes";
import type { DraftRecorder } from "./recorder";
import { codeSection, detailNumber, inchesForLength, requirementNote } from "./vocabulary";

export function labelNode(d: DraftRecorder, node: DraftNode) {
  if (node.kind === "bubble" || node.kind === "section") return;
  const text = node.kind === "turning" ? '60" dia' : requirementNote(d.rng);
  const size = d.fontSize(0.62);
  const placed = d.textClear(text, node.x, node.y - node.ry - d.unit * 0.45, size, { align: "center", baseline: "bottom" });
  if (!placed) return;
  const halfWidth = d.measure(text, size) / 2;
  const underlineY = placed[1] + d.unit * 0.12;
  d.line([[placed[0] - halfWidth, underlineY], [placed[0] + halfWidth, underlineY]], "thin");
}

/** Swaps x and y so one dimension routine can draw both horizontal and vertical strings. */
type Axis = { along: (p: Point) => number; across: (p: Point) => number; point: (along: number, across: number) => Point; rotation: number };

const HORIZONTAL: Axis = { along: (p) => p[0], across: (p) => p[1], point: (along, across) => [along, across], rotation: 0 };
const VERTICAL: Axis = { along: (p) => p[1], across: (p) => p[0], point: (along, across) => [across, along], rotation: -HALF_PI };

function dimensionString(d: DraftRecorder, axis: Axis, a: Point, b: Point, sign: number, offset: number) {
  const tick = d.unit * 0.22;
  const across = d.snap((sign < 0 ? Math.min(axis.across(a), axis.across(b)) : Math.max(axis.across(a), axis.across(b))) + offset);
  for (const end of [a, b]) {
    d.line([axis.point(axis.along(end), axis.across(end) + sign * d.unit * 0.6), axis.point(axis.along(end), across + sign * d.unit * 0.5)], "thin");
  }
  d.line([axis.point(axis.along(a), across), axis.point(axis.along(b), across)], "thin");
  for (const end of [a, b]) {
    const [x, y] = axis.point(axis.along(end), across);
    d.line([[x - tick, y + tick], [x + tick, y - tick]], "regular");
  }
  const label = inchesForLength(Math.abs(axis.along(b) - axis.along(a)), d.unit);
  const [labelX, labelY] = axis.point((axis.along(a) + axis.along(b)) / 2, across - d.unit * 0.15);
  d.textClear(label, labelX, labelY, d.fontSize(0.6), { align: "center", baseline: "bottom", rotation: axis.rotation });
}

function dimension(d: DraftRecorder, node: DraftNode, previous: DraftNode | null) {
  if (!previous) return;
  const horizontal = Math.abs(node.x - previous.x) >= Math.abs(node.y - previous.y);
  const axis = horizontal ? HORIZONTAL : VERTICAL;
  const a: Point = [previous.x, previous.y];
  const b: Point = [node.x, node.y];
  if (Math.abs(axis.along(b) - axis.along(a)) < d.unit * 2) return;
  const sign = d.rng.sign();
  dimensionString(d, axis, a, b, sign, d.unit * d.rng.float(2.5, 4.5) * sign);
}

function findFreeSpot(d: DraftRecorder, node: DraftNode, radius: number): Point | null {
  for (let attempt = 0; attempt < 8; attempt++) {
    const angle = d.rng.float(0, Math.PI * 2);
    const reach = d.unit * d.rng.float(3, 5) + node.r;
    const x = d.snap(node.x + Math.cos(angle) * reach);
    const y = d.snap(node.y + Math.sin(angle) * reach);
    if (d.occupancy.isFree(boxAround(x, y, radius))) return [x, y];
  }
  return null;
}

function callout(d: DraftRecorder, node: DraftNode) {
  const radius = d.unit * 1.1;
  const spot = findFreeSpot(d, node, radius);
  if (!spot) return;
  const [cx, cy] = spot;
  d.occupancy.claim(boxAround(cx, cy, radius));
  const angle = Math.atan2(node.y - cy, node.x - cx);
  d.line([[node.x, node.y], [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius]], "thin");
  if (d.rng.chance(0.5)) d.dot(node.x, node.y, d.unit * 0.12);
  drawCalloutBubble(d, cx, cy, radius);
}

function contourPoints(node: DraftNode, width: number, height: number, rotation: number): Point[] {
  const local: Point[] = [[-width / 2, height], [-width / 2, 0], ...arcPoints(0, 0, width / 2, Math.PI, Math.PI * 2), [width / 2, height]];
  const [cos, sin] = [Math.cos(rotation), Math.sin(rotation)];
  return local.map(([px, py]) => [node.x + px * cos - py * sin, node.y + px * sin + py * cos] as const);
}

function contours(d: DraftRecorder, node: DraftNode) {
  const count = d.rng.int(3, 7);
  const rotation = d.rng.int(0, 4) * HALF_PI;
  const step = d.unit * 0.45;
  for (let i = 0; i < count; i++) {
    const outermost = i === count - 1;
    const points = contourPoints(node, node.rx * 2 + d.unit * 1.2 + i * step * 2, node.ry + d.unit * 1.2 + i * step, rotation);
    d.line(points, outermost ? "regular" : "thin");
    if (outermost) d.occupancy.claim(boundsOf(points));
  }
}

function hatchLines(d: DraftRecorder, x: number, y: number, width: number, height: number) {
  const step = d.unit * 0.28;
  for (let offset = step; offset < width + height; offset += step) {
    const from: Point = offset <= width ? [x + offset, y] : [x + width, y + offset - width];
    const to: Point = offset <= height ? [x, y + offset] : [x + offset - height, y + height];
    d.line([from, to], "thin");
  }
}

function hatch(d: DraftRecorder, node: DraftNode) {
  const width = d.unit * d.rng.float(1.5, 3);
  const height = d.unit * d.rng.float(0.6, 1.2);
  const x = d.snap(node.x + d.unit * d.rng.float(-4, 4));
  const y = d.snap(node.y + d.unit * d.rng.float(1.5, 3.5) * d.rng.sign());
  const box: Box = [x, y, x + width, y + height];
  if (!d.occupancy.isFree(box)) return;
  d.occupancy.claim(box);
  d.line(rectPoints(x, y, width, height), "thin");
  hatchLines(d, x, y, width, height);
}

function leaderNote(d: DraftRecorder, node: DraftNode) {
  const text = codeSection(d.rng);
  const size = d.fontSize(0.6);
  const textWidth = d.measure(text, size);
  for (const angle of d.rng.shuffled([-QUARTER_PI, -3 * QUARTER_PI, QUARTER_PI, 3 * QUARTER_PI])) {
    const reach = d.unit * d.rng.float(2.5, 4.5) + node.r;
    const elbowX = d.snap(node.x + Math.cos(angle) * reach);
    const elbowY = d.snap(node.y + Math.sin(angle) * reach);
    const direction = Math.cos(angle) > 0 ? 1 : -1;
    const [textX, textY] = [elbowX + direction * d.unit * 0.15, elbowY - d.unit * 0.1];
    const placement = { align: direction > 0 ? "left" : "right", baseline: "bottom" } as const;
    const box = d.textBox(text, textX, textY, size, placement);
    if (!d.occupancy.isFree(box)) continue;
    d.occupancy.claim(box);
    const start: Point = [node.x + Math.cos(angle) * node.r * 0.6, node.y + Math.sin(angle) * node.r * 0.6];
    d.line([start, [elbowX, elbowY], [elbowX + direction * (textWidth + d.unit * 0.3), elbowY]], "thin");
    d.textAt(text, textX, textY, size, placement);
    return;
  }
}

function keynoteArrow(d: DraftRecorder, node: DraftNode) {
  const x = d.snap(node.x + d.unit * d.rng.float(-3, 3));
  const y = d.snap(node.y + d.unit * d.rng.float(2, 4) * d.rng.sign());
  const direction = d.rng.sign();
  const text = detailNumber(d.rng);
  const size = d.fontSize(0.6);
  const placement = { align: direction > 0 ? "right" : "left" } as const;
  const textX = x - direction * d.unit * 0.15;
  const box = d.textBox(text, textX, y, size, placement);
  const headX = x + direction * d.unit * 1.6;
  if (!d.occupancy.isFree([Math.min(box[0], headX), box[1], Math.max(box[2], headX), box[3]])) return;
  d.occupancy.claim(box);
  d.line([[x, y], [headX, y]], "thin");
  d.blot([[headX, y], [headX - direction * d.unit * 0.35, y - d.unit * 0.2], [headX - direction * d.unit * 0.35, y + d.unit * 0.2]]);
  d.textAt(text, textX, y, size, placement);
}

function gridLine(d: DraftRecorder, node: DraftNode) {
  const horizontal = d.rng.chance(0.5);
  const length = d.unit * d.rng.float(10, 26) * d.rng.sign();
  const endX = d.snap(horizontal ? node.x + length : node.x);
  const endY = d.snap(horizontal ? node.y : node.y + length);
  const markerBox = boxAround(endX, endY, d.unit * 1.8);
  if (!d.occupancy.isFree(markerBox)) return;
  d.occupancy.claim(markerBox);
  const dash = d.rng.chance(0.5) ? ([d.unit * 0.9, d.unit * 0.35] as const) : undefined;
  d.line([[node.x, node.y], [endX, endY]], "thin", { dash });
  drawSectionMarker(d, endX, endY, d.unit * 0.85);
}

function doorSwing(d: DraftRecorder, node: DraftNode) {
  const leaf = d.unit * 6;
  const hingeX = d.snap(node.x + d.rng.sign() * (node.rx + d.unit));
  const hingeY = d.snap(node.y + d.rng.sign() * (node.ry + d.unit));
  const from = d.rng.int(0, 4) * HALF_PI;
  const swing = arcPoints(hingeX, hingeY, leaf, from, from + HALF_PI);
  const box = boundsOf([[hingeX, hingeY], ...swing]);
  if (!d.occupancy.isFree(box)) return;
  d.occupancy.claim(box);
  d.line([[hingeX, hingeY], swing[swing.length - 1]!], "regular");
  d.line(swing, "thin");
}

interface Decoration {
  odds: number;
  draw: (d: DraftRecorder, node: DraftNode, previous: DraftNode | null) => void;
}

const DECORATIONS: Decoration[] = [
  { odds: 0.45, draw: dimension },
  { odds: 0.35, draw: callout },
  { odds: 0.2, draw: contours },
  { odds: 0.15, draw: hatch },
  { odds: 0.3, draw: leaderNote },
  { odds: 0.1, draw: keynoteArrow },
  { odds: 0.12, draw: gridLine },
  { odds: 0.12, draw: doorSwing },
];

/** Adds the incidental drafting around a node: dimensions, callouts, code notes, hatches and so on. */
export function decorate(d: DraftRecorder, node: DraftNode, previous: DraftNode | null) {
  for (const decoration of DECORATIONS) {
    if (d.rng.chance(decoration.odds)) d.attempt(() => decoration.draw(d, node, previous));
  }
  if (!previous && d.rng.chance(0.5)) d.attempt(() => callout(d, node));
}
