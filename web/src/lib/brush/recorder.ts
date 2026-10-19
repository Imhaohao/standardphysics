import { arcPoints, boundsOf, inflateBox, roundedRectPoints, splitDashes, TAU, type Box, type Point } from "./geometry";
import { createRun, INK, LABEL_SCALE, LINE_WEIGHT, type InkMark, type LineWeight, type Mark, type TextAlign, type TextBaseline } from "./marks";
import type { Occupancy } from "./occupancy";
import type { Random } from "./random";

export type MeasureText = (text: string, size: number) => number;
export type Dash = readonly [number, number];

export const ALIGN_OFFSET: Record<TextAlign, number> = { left: 0, center: -0.5, right: -1 };
const BASELINE_OFFSET: Record<TextBaseline, number> = { top: 0, middle: -0.5, bottom: -1 };

export interface TextPlacement {
  align?: TextAlign;
  baseline?: TextBaseline;
  rotation?: number;
}

export interface LineOptions {
  dash?: Dash;
  fill?: boolean;
  color?: string;
}

interface CircleOptions extends LineOptions {
  from?: number;
  to?: number;
}

const TEXT_NUDGES: readonly Point[] = [[0, 0], [0, -1], [0, 1], [1, 0], [-1, 0], [0, -2], [0, 2], [1, -1], [1, 1], [-1, -1], [-1, 1]];

function rotatedBounds(x: number, y: number, rotation: number, corners: Point[]): Box {
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  return boundsOf(corners.map(([px, py]) => [x + px * cos - py * sin, y + px * sin + py * cos] as const));
}

function inkBounds(mark: InkMark): Box {
  const [x0, y0, x1, y1] = inflateBox(boundsOf(mark.runs.flatMap((run) => run.points)), mark.weight * (INK.bleedReach * 1.6 + 3));
  const longestDrip = Math.max(0, ...mark.runs.flatMap((run) => run.blobs.map((blob) => blob.drip)));
  return [x0, y0, x1, y1 + longestDrip];
}

/** Collects the marks of one gesture, checking each against the sheet's occupancy before it is kept. */
export class DraftRecorder {
  readonly marks: Mark[] = [];

  constructor(
    readonly unit: number,
    readonly occupancy: Occupancy,
    private readonly measureText: MeasureText,
    readonly rng: Random,
  ) {}

  snap(value: number) {
    const step = this.unit * 0.5;
    return Math.round(value / step) * step;
  }

  fontSize(multiplier = 0.72) {
    return Math.max(6.5, this.unit * multiplier * 0.92) * LABEL_SCALE;
  }

  measure(text: string, size: number) {
    return this.measureText(text, size);
  }

  line(points: readonly Point[], weight: LineWeight, options: LineOptions = {}) {
    if (points.length < 2) return;
    const pieces = options.dash ? splitDashes(points, options.dash[0], options.dash[1]) : [points];
    const runs = pieces.map((piece) => createRun(this.rng, piece, this.unit));
    const length = runs.reduce((sum, run) => sum + run.length, 0);
    if (length <= 0) return;
    const fillPolygon = options.fill ? [...points] : null;
    this.marks.push({ kind: "ink", runs, weight: LINE_WEIGHT[weight], length, fillPolygon, color: options.color, start: 0, duration: 0 });
  }

  circle(cx: number, cy: number, radius: number, weight: LineWeight, options: CircleOptions = {}) {
    const { from = 0, to = TAU, ...lineOptions } = options;
    this.line(arcPoints(cx, cy, radius, from, to), weight, lineOptions);
  }

  roundedRect(x: number, y: number, width: number, height: number, radius: number, weight: LineWeight, fill = false) {
    this.line(roundedRectPoints(x, y, width, height, radius), weight, { fill });
  }

  textAt(text: string, x: number, y: number, size: number, placement: TextPlacement = {}, color?: string) {
    const { align = "left", baseline = "middle", rotation = 0 } = placement;
    this.marks.push({ kind: "text", text, x, y, size, align, baseline, rotation, color, start: 0, duration: 0 });
  }

  /** Writes the text at the first nearby spot that is free, nudging by whole grid units. */
  textClear(text: string, x: number, y: number, size: number, placement: TextPlacement = {}): Point | null {
    for (const [nx, ny] of TEXT_NUDGES) {
      const [tx, ty] = [x + nx * this.unit, y + ny * this.unit];
      const box = this.textBox(text, tx, ty, size, placement);
      if (!this.occupancy.isFree(box)) continue;
      this.occupancy.claim(box);
      this.textAt(text, tx, ty, size, placement);
      return [tx, ty];
    }
    return null;
  }

  textBox(text: string, x: number, y: number, size: number, placement: TextPlacement = {}): Box {
    const { align = "left", baseline = "middle", rotation = 0 } = placement;
    const width = this.measure(text, size);
    const left = ALIGN_OFFSET[align] * width;
    const top = BASELINE_OFFSET[baseline] * size;
    const corners: Point[] = [[left, top], [left + width, top], [left, top + size], [left + width, top + size]];
    return inflateBox(rotatedBounds(x, y, rotation, corners), this.unit * 0.22);
  }

  /** Runs `draw`, and throws away everything it recorded if any of it landed somewhere the pen may not go. */
  attempt(draw: () => void): boolean {
    const markCount = this.marks.length;
    const claimCount = this.occupancy.claimCount;
    draw();
    const added = this.marks.slice(markCount);
    if (added.every((mark) => this.occupancy.isAllowed(this.boundsOfMark(mark)))) return true;
    this.marks.length = markCount;
    this.occupancy.rollbackTo(claimCount);
    return false;
  }

  boundsOfMark(mark: Mark): Box {
    if (mark.kind === "ink") return inkBounds(mark);
    if (mark.kind === "text") return this.textBox(mark.text, mark.x, mark.y, mark.size, mark);
    if (mark.kind === "speck") return boundsOf(mark.specks.map((speck) => [speck.x, speck.y] as const));
    if (mark.kind === "erase") return boundsOf(mark.points);
    return inflateBox(boundsOf(mark.points), 2);
  }

  blot(outline: readonly Point[], color?: string) {
    const cx = outline.reduce((sum, point) => sum + point[0], 0) / outline.length;
    const cy = outline.reduce((sum, point) => sum + point[1], 0) / outline.length;
    const points = outline.map(([x, y]) => {
      const length = Math.hypot(x - cx, y - cy) || 1;
      const offset = this.rng.float(-1, 1) * INK.raggedness;
      return [x + ((x - cx) / length) * offset, y + ((y - cy) / length) * offset] as const;
    });
    this.marks.push({ kind: "blot", points, cx, cy, color, start: 0, duration: 0 });
  }

  erase(polygon: readonly Point[]) {
    this.marks.push({ kind: "erase", points: [...polygon], start: 0, duration: 0 });
  }

  dot(x: number, y: number, radius: number, color?: string) {
    const outline = Array.from({ length: 14 }, (_, i) => [x + Math.cos((i / 14) * TAU) * radius, y + Math.sin((i / 14) * TAU) * radius] as const);
    this.blot(outline, color);
  }
}
