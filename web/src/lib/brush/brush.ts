import { decorate, labelNode } from "./decorations";
import { boundsOf, boxesOverlap, type Box, type Point } from "./geometry";
import { INK, markDuration, specksAround, type Mark, type Stamp } from "./marks";
import { createNode, drawNode, type DraftNode } from "./nodes";
import { Occupancy } from "./occupancy";
import { Random } from "./random";
import { DraftRecorder, type MeasureText } from "./recorder";
import { connect } from "./wiring";

const NODE_SPACING_UNITS = 6;
const MINIMUM_NODE_GAP_UNITS = 2.5;
const FOLLOWER_SUBSTEPS = 4;
const PEN_OVERLAP = 0.8;

interface StrokeState {
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  pressed: boolean;
  travel: number;
  nodes: DraftNode[];
}

export interface SchematicBrushOptions {
  unit: number;
  measureText: MeasureText;
  now: () => number;
  speed?: number;
  random?: Random;
  /** Draws a little ink splatter near the start of some gestures. Off for plans, where it reads as dirt. */
  specks?: boolean;
}

/**
 * A procedural drafting pen. A stroke along a route sets down drafting symbols every few grid units, joins
 * them, and decorates them with dimensions and notes; `stampWith` records arbitrary drafting. Every gesture
 * becomes a Stamp scheduled on the pen clock, which a renderer draws progressively.
 */
export class SchematicBrush {
  private stroke: StrokeState | null = null;
  private stamps: Stamp[] = [];
  private scheduleOffset = 0;
  private inkedAreas: Box[] = [];
  private readonly occupancy = new Occupancy();
  private readonly rng: Random;

  constructor(private readonly options: SchematicBrushOptions) {
    this.rng = options.random ?? new Random();
  }

  get activeStamps(): readonly Stamp[] {
    return this.stamps;
  }

  /** True while a pointer stroke is still catching up or stamps are left to draw. */
  get busy() {
    return this.stroke !== null || this.stamps.length > 0;
  }

  /** The earliest time any pending stamp starts drawing, so an idle loop can sleep until then. */
  get nextStartAt() {
    return this.stamps.reduce((earliest, stamp) => Math.min(earliest, stamp.startsAt), Infinity);
  }

  pointerDown(x: number, y: number) {
    this.stroke = { x, y, targetX: x, targetY: y, pressed: true, travel: 0, nodes: [] };
  }

  pointerMove(x: number, y: number) {
    if (!this.stroke) return;
    this.stroke.targetX = x;
    this.stroke.targetY = y;
  }

  pointerUp() {
    if (this.stroke) this.stroke.pressed = false;
  }

  /** Advances the pen and hands back the stamps whose ink has finished drawing. */
  tick(): Stamp[] {
    this.advanceStroke();
    const now = this.options.now();
    const finished = this.stamps.filter((stamp) => now >= stamp.endsAt);
    this.stamps = this.stamps.filter((stamp) => now < stamp.endsAt);
    return finished;
  }

  takeAll(): Stamp[] {
    while (this.stroke) this.advanceStroke(true);
    const all = this.stamps;
    this.stamps = [];
    return all;
  }

  clear() {
    this.stroke = null;
    this.stamps = [];
    this.inkedAreas = [];
    this.occupancy.clear();
  }

  setKeepOuts(keepOuts: readonly Box[], bounds: Box | null) {
    this.occupancy.setKeepOuts(keepOuts, bounds);
  }

  inkTouches(boxes: readonly Box[]) {
    return this.inkedAreas.some((inked) => boxes.some((box) => boxesOverlap(inked, box)));
  }

  draftRoute(route: readonly Point[], durationMs: number, startDelayMs = 0) {
    if (route.length < 2) return;
    this.pointerDown(route[0]![0], route[0]![1]);
    route.forEach(([x, y], index) => {
      this.scheduleOffset = startDelayMs + (index / (route.length - 1)) * durationMs;
      this.strokeTo(x, y);
    });
    this.endStroke();
    this.scheduleOffset = 0;
  }

  stampWith(draw: (recorder: DraftRecorder) => void, startDelayMs = 0) {
    const recorder = this.recorder();
    draw(recorder);
    this.scheduleOffset = startDelayMs;
    this.commit(recorder);
    this.scheduleOffset = 0;
  }

  private recorder() {
    return new DraftRecorder(this.options.unit, this.occupancy, this.options.measureText, this.rng);
  }

  private advanceStroke(release = false) {
    const stroke = this.stroke;
    if (!stroke) return;
    if (release) stroke.pressed = false;
    for (let substep = 0; substep < FOLLOWER_SUBSTEPS; substep++) {
      const [dx, dy] = [stroke.targetX - stroke.x, stroke.targetY - stroke.y];
      const gap = Math.hypot(dx, dy);
      if (gap < 0.4) break;
      const step = Math.min(gap, Math.max(1.5, gap * 0.15));
      this.strokeTo(stroke.x + (dx / gap) * step, stroke.y + (dy / gap) * step);
    }
    if (!stroke.pressed && Math.hypot(stroke.targetX - stroke.x, stroke.targetY - stroke.y) < 0.8) this.endStroke();
  }

  private strokeTo(x: number, y: number) {
    const stroke = this.stroke;
    if (!stroke) return;
    const travelled = Math.hypot(x - stroke.x, y - stroke.y);
    if (travelled < 0.3) return;
    stroke.travel += travelled;
    stroke.x = x;
    stroke.y = y;
    if (stroke.travel < this.options.unit * NODE_SPACING_UNITS) return;
    stroke.travel = 0;
    this.placeNode(stroke, x, y);
  }

  private endStroke() {
    const stroke = this.stroke;
    if (stroke && stroke.nodes.length === 0) this.placeNode(stroke, stroke.x, stroke.y);
    this.stroke = null;
  }

  private placeNode(stroke: StrokeState, rawX: number, rawY: number) {
    const recorder = this.recorder();
    const [x, y] = [recorder.snap(rawX), recorder.snap(rawY)];
    const previous = stroke.nodes.at(-1) ?? null;
    if (previous && Math.hypot(previous.x - x, previous.y - y) < this.options.unit * MINIMUM_NODE_GAP_UNITS) return;
    const node = createNode(this.rng, x, y, this.options.unit);
    const placed = recorder.attempt(() => {
      this.occupancy.claim([x - node.rx, y - node.ry, x + node.rx, y + node.ry]);
      if (previous) connect(recorder, previous, node);
      drawNode(recorder, node);
      if (this.rng.chance(0.85)) labelNode(recorder, node);
    });
    if (!placed) return;
    decorate(recorder, node, previous);
    stroke.nodes.push(node);
    this.commit(recorder);
  }

  private specksFor(marks: Mark[]) {
    if (this.options.specks === false) return null;
    const firstInk = marks.find((mark) => mark.kind === "ink");
    if (!firstInk || !this.rng.chance(INK.speckChance)) return null;
    const specks = specksAround(this.rng, firstInk.runs[0]!.points[0]!, this.options.unit);
    specks.specks = specks.specks.filter((speck) => this.occupancy.isAllowed(boundsOf([[speck.x, speck.y]])));
    return specks;
  }

  private commit(recorder: DraftRecorder) {
    const marks = recorder.marks;
    if (marks.length === 0) return;
    this.inkedAreas.push(...marks.map((mark) => recorder.boundsOfMark(mark)));
    const specks = this.specksFor(marks);
    if (specks) marks.push(specks);
    const speed = this.options.speed ?? 1;
    let [penTime, endsAt] = [0, 0];
    for (const mark of marks) {
      mark.duration = markDuration(mark, speed);
      mark.start = penTime;
      penTime += mark.duration * PEN_OVERLAP;
      endsAt = Math.max(endsAt, mark.start + mark.duration);
    }
    const startsAt = this.options.now() + this.scheduleOffset;
    this.stamps.push({ marks, startsAt, endsAt: startsAt + endsAt });
  }
}
