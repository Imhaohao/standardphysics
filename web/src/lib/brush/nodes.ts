import { rectPoints, type Point } from "./geometry";
import type { Random } from "./random";
import type { DraftRecorder } from "./recorder";
import { detailNumber, INCHES_PER_UNIT, sheetReference } from "./vocabulary";

export type NodeKind = "bubble" | "turning" | "section" | "terminal" | "fixture" | "pin";

/** A drafting symbol the pen sets down along its route. `rx`/`ry` are its half extents. */
export interface DraftNode {
  x: number;
  y: number;
  kind: NodeKind;
  r: number;
  rx: number;
  ry: number;
}

const NODE_WEIGHTS: readonly (readonly [NodeKind, number])[] = [
  ["bubble", 6],
  ["terminal", 3],
  ["fixture", 3],
  ["section", 2],
  ["turning", 2],
  ["pin", 2],
];

const TURNING_SPACE_DIAMETER_INCHES = 60;

type Extents = (rng: Random, unit: number, r: number) => [rx: number, ry: number, r?: number];

const EXTENTS: Record<NodeKind, Extents> = {
  pin: (_, __, r) => [r, r],
  fixture: (rng, unit) => [unit * rng.float(1.8, 2.6), unit * rng.float(1, 1.5)],
  terminal: (_, unit) => [unit * 0.55, unit * 0.55, unit * 0.55],
  bubble: (_, unit) => [unit * 1.15, unit * 1.15, unit * 1.15],
  section: (_, __, r) => [r * 1.9, r * 1.45],
  turning: (_, unit) => {
    const radius = (TURNING_SPACE_DIAMETER_INCHES / 2 / INCHES_PER_UNIT) * unit;
    return [radius, radius, radius];
  },
};

export function createNode(rng: Random, x: number, y: number, unit: number): DraftNode {
  const kind = rng.weighted(NODE_WEIGHTS);
  const baseRadius = unit * rng.float(0.8, 1.2);
  const [rx, ry, r = baseRadius] = EXTENTS[kind](rng, unit, baseRadius);
  return { x, y, kind, r, rx, ry };
}

const COMPASS: readonly Point[] = [[1, 0], [-1, 0], [0, 1], [0, -1]];

function drawPin(d: DraftRecorder, { x, y, r }: DraftNode) {
  d.circle(x, y, r, "regular", { fill: true });
  d.circle(x, y, r * 0.42, "thin");
  for (const [dx, dy] of COMPASS) d.line([[x + dx * r * 0.7, y + dy * r * 0.7], [x + dx * r * 1.45, y + dy * r * 1.45]], "thin");
  if (d.rng.chance(0.3)) d.circle(x, y, r * 1.9, "thin", { dash: [d.unit * 0.3, d.unit * 0.25] });
}

function drawCrosshair(d: DraftRecorder, x: number, y: number, width: number, height: number) {
  const [cx, cy] = [x + width / 2, y + height / 2];
  d.circle(cx, cy, height * 0.28, "thin");
  d.line([[cx - height * 0.4, cy], [cx + height * 0.4, cy]], "thin");
  d.line([[cx, cy - height * 0.4], [cx, cy + height * 0.4]], "thin");
}

function drawShelves(d: DraftRecorder, x: number, y: number, width: number, height: number) {
  const shelves = Math.floor(d.rng.float(1, 4));
  for (let i = 1; i <= shelves; i++) {
    const shelfY = y + (height * i) / (shelves + 1);
    d.line([[x + d.unit * 0.4, shelfY], [x + width - d.unit * 0.4, shelfY]], "thin");
  }
}

function drawKnobs(d: DraftRecorder, x: number, y: number, width: number, height: number) {
  const knobs = Math.floor(d.rng.float(2, 5));
  for (let i = 0; i < knobs; i++) d.circle(x + (width * (i + 0.5)) / knobs, y + height - d.unit * 0.45, d.unit * 0.2, "thin");
}

function drawFixture(d: DraftRecorder, node: DraftNode) {
  const [x, y, width, height] = [node.x - node.rx, node.y - node.ry, node.rx * 2, node.ry * 2];
  d.roundedRect(x, y, width, height, d.unit * 0.3, "regular", true);
  const variant = d.rng.next();
  const detail = variant < 0.4 ? drawCrosshair : variant < 0.7 ? drawShelves : drawKnobs;
  detail(d, x, y, width, height);
}

function drawTerminal(d: DraftRecorder, { x, y, r }: DraftNode) {
  if (d.rng.chance(0.5)) {
    d.line(rectPoints(x - r, y - r, r * 2, r * 2), "regular", { fill: true });
    d.dot(x, y, r * 0.3);
    return;
  }
  d.circle(x, y, r, "regular", { fill: true });
  d.circle(x, y, r * 0.62, "thin");
  d.dot(x, y, r * 0.22);
}

export function drawCalloutBubble(d: DraftRecorder, x: number, y: number, r: number, label = detailNumber(d.rng), reference = sheetReference(d.rng)) {
  d.circle(x, y, r, "regular", { fill: true });
  d.line([[x - r, y], [x + r, y]], "thin");
  d.textAt(label, x, y - d.unit * 0.1, d.fontSize(0.66), { align: "center", baseline: "bottom" });
  d.textAt(reference, x, y + d.unit * 0.12, d.fontSize(0.5), { align: "center", baseline: "top" });
}

export function drawSectionMarker(d: DraftRecorder, x: number, y: number, r: number) {
  const halfWidth = r * 1.9;
  const halfHeight = r * 1.45;
  d.line([[x, y - halfHeight], [x + halfWidth, y], [x, y + halfHeight], [x - halfWidth, y], [x, y - halfHeight]], "regular", { fill: true });
  d.line([[x - halfWidth, y], [x + halfWidth, y]], "thin");
  d.textAt(detailNumber(d.rng), x, y - halfHeight * 0.4, d.fontSize(0.5), { align: "center" });
  d.textAt(sheetReference(d.rng), x, y + halfHeight * 0.42, d.fontSize(0.38), { align: "center" });
  const [dx, dy] = d.rng.pick<Point>([[0, -1], [0, 1], [-1, 0], [1, 0]]);
  const extent = dx === 0 ? halfHeight : halfWidth;
  const [baseX, baseY] = [x + dx * extent, y + dy * extent];
  const spread = halfHeight * 0.4;
  d.blot([
    [x + dx * (extent + halfHeight * 0.7), y + dy * (extent + halfHeight * 0.7)],
    [baseX + dy * spread, baseY + dx * spread],
    [baseX - dy * spread, baseY - dx * spread],
  ]);
}

function drawTurningSpace(d: DraftRecorder, { x, y, r }: DraftNode) {
  d.circle(x, y, r, "regular", { dash: [d.unit * 0.5, d.unit * 0.35] });
  d.circle(x, y, r * 0.62, "thin");
  d.circle(x, y, r * 0.3, "thin");
  d.line([[x - r * 0.15, y], [x + r * 0.15, y]], "thin");
  d.line([[x, y - r * 0.15], [x, y + r * 0.15]], "thin");
}

const DRAWERS: Record<NodeKind, (d: DraftRecorder, node: DraftNode) => void> = {
  pin: drawPin,
  fixture: drawFixture,
  terminal: drawTerminal,
  bubble: (d, node) => drawCalloutBubble(d, node.x, node.y, node.r),
  section: (d, node) => drawSectionMarker(d, node.x, node.y, node.r),
  turning: drawTurningSpace,
};

export function drawNode(d: DraftRecorder, node: DraftNode) {
  DRAWERS[node.kind](d, node);
}
