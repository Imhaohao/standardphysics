import { clamp, cutPolyline, TAU, type Point } from "./geometry";
import { INK, type BlotMark, type EraseMark, type InkMark, type InkRun, type Mark, type SpeckMark, type Stamp, type TextMark } from "./marks";
import { smoothNoise } from "./random";
import { ALIGN_OFFSET } from "./recorder";

export interface InkPalette {
  ink: string;
  paper: string;
  fontFamily: string;
}

type Context = CanvasRenderingContext2D;

const BLEED_LAYERS: readonly [reach: number, alpha: number][] = [
  [1, 0.16],
  [0.6, 0.38],
  [0.33, 1],
];

function easeOutBack(progress: number) {
  const overshoot = 1.4;
  return 1 + (overshoot + 1) * (progress - 1) ** 3 + overshoot * (progress - 1) ** 2;
}

function strokeSegment(ctx: Context, from: Point, to: Point, width: number, alpha: number) {
  ctx.globalAlpha = alpha;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(from[0], from[1]);
  ctx.lineTo(to[0], to[1]);
  ctx.stroke();
}

function fillDisc(ctx: Context, x: number, y: number, diameter: number, alpha: number) {
  ctx.globalAlpha = alpha;
  ctx.beginPath();
  ctx.arc(x, y, Math.max(0, diameter / 2), 0, TAU);
  ctx.fill();
}

function tracePolygon(ctx: Context, points: readonly Point[]) {
  ctx.beginPath();
  points.forEach(([x, y], index) => (index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
  ctx.closePath();
}

function forEachSegment(points: readonly Point[], visit: (from: Point, to: Point, index: number) => void) {
  for (let i = 1; i < points.length; i++) visit(points[i - 1]!, points[i]!, i);
}

/** Three widening, fading passes under the stroke: the ink wicking into the paper fibres. */
function bleedRun(ctx: Context, run: InkRun, points: readonly Point[], weight: number) {
  const reach = weight * INK.bleedReach;
  for (const [reachShare, alphaShare] of BLEED_LAYERS) {
    forEachSegment(points, (from, to, i) => {
      const slow = smoothNoise(run.seed + 40 + i * 0.11) ** 1.7;
      const fast = smoothNoise(run.seed + 60 + i * 0.55);
      const spread = 0.15 + 1.3 * slow + 0.6 * fast * slow;
      strokeSegment(ctx, from, to, weight + reach * reachShare * spread, INK.bleedAlpha * alphaShare);
    });
  }
}

function fiber(ctx: Context, run: InkRun, at: Point, normal: Point, i: number, weight: number, side: number) {
  const length = weight * INK.bleedReach * (0.3 + 1.2 * smoothNoise(run.seed + 170 + i * 0.9)) * side;
  const end: Point = [at[0] + normal[0] * length, at[1] + normal[1] * length];
  strokeSegment(ctx, at, end, Math.max(0.35, weight * 0.3), 0.14 + 0.2 * smoothNoise(run.seed + 210 + i * 0.7));
}

function grain(ctx: Context, run: InkRun, at: Point, normal: Point, i: number, weight: number, side: number) {
  const offset = (weight * 0.6 + weight * INK.bleedReach * 0.9 * smoothNoise(run.seed + 330 + i * 1.1)) * -side;
  const radius = 0.25 + 0.55 * smoothNoise(run.seed + 370 + i * 0.8);
  fillDisc(ctx, at[0] + normal[0] * offset, at[1] + normal[1] * offset, radius * 2, 0.16 + 0.35 * smoothNoise(run.seed + 410 + i * 0.6));
}

function fibersAndGrains(ctx: Context, run: InkRun, points: readonly Point[], weight: number) {
  forEachSegment(points, (from, to, i) => {
    const length = Math.hypot(to[0] - from[0], to[1] - from[1]) || 1;
    const normal: Point = [-(to[1] - from[1]) / length, (to[0] - from[0]) / length];
    const side = smoothNoise(run.seed + 130 + i * 1.3) < 0.5 ? -1 : 1;
    if (smoothNoise(run.seed + 90 + i * 2.3) > 1 - INK.fiberChance) fiber(ctx, run, to, normal, i, weight, side);
    if (smoothNoise(run.seed + 250 + i * 3.1) > 1 - INK.grainChance) grain(ctx, run, to, normal, i, weight, side);
  });
}

function inkBody(ctx: Context, run: InkRun, points: readonly Point[], weight: number) {
  forEachSegment(points, (from, to, i) => strokeSegment(ctx, from, to, weight * (0.5 + 1.2 * smoothNoise(run.seed + i * 0.2)), INK.bodyAlpha));
}

function poolBleed(ctx: Context, seed: number, x: number, y: number, diameter: number) {
  fillDisc(ctx, x, y, diameter * 2.2, 0.07);
  for (let lobe = 0; lobe < 3; lobe++) {
    const angle = smoothNoise(seed + lobe * 3.1) * TAU * 2;
    const offset = diameter * (0.3 + 0.5 * smoothNoise(seed + 50 + lobe * 2.7));
    const size = diameter * (0.9 + 0.8 * smoothNoise(seed + 110 + lobe * 1.9));
    fillDisc(ctx, x + Math.cos(angle) * offset, y + Math.sin(angle) * offset, size, 0.055 + 0.05 * smoothNoise(seed + 80 + lobe));
  }
}

function pool(ctx: Context, seed: number, at: Point, diameter: number) {
  poolBleed(ctx, seed, at[0], at[1], diameter);
  fillDisc(ctx, at[0], at[1], diameter, 0.88);
}

/** Ink gathers where the nib lands and where it lifts. */
function inkPools(ctx: Context, run: InkRun, points: readonly Point[], weight: number, complete: boolean) {
  if (!run.pooled) return;
  pool(ctx, run.seed + 7, points[0]!, weight * 3);
  if (complete) pool(ctx, run.seed + 11, points[points.length - 1]!, weight * 2.5);
}

function inkBlobs(ctx: Context, run: InkRun, points: readonly Point[], weight: number) {
  for (const blob of run.blobs) {
    const at = points[blob.index];
    if (!at) continue;
    const [x, y] = at;
    fillDisc(ctx, x, y, weight * blob.size, 0.88);
    if (blob.drip <= 0) continue;
    strokeSegment(ctx, [x, y], [x, y + blob.drip * 0.7], weight * 1.1, 0.82);
    strokeSegment(ctx, [x, y + blob.drip * 0.7], [x, y + blob.drip], weight * 0.6, 0.82);
    fillDisc(ctx, x, y + blob.drip, weight * 1.6, 0.88);
  }
}

function drawRun(ctx: Context, run: InkRun, points: readonly Point[], weight: number, complete: boolean) {
  if (points.length < 2) return;
  bleedRun(ctx, run, points, weight);
  fibersAndGrains(ctx, run, points, weight);
  inkBody(ctx, run, points, weight);
  inkPools(ctx, run, points, weight, complete);
  inkBlobs(ctx, run, points, weight);
}

function knockOutFill(ctx: Context, polygon: readonly Point[], palette: InkPalette) {
  ctx.globalAlpha = 1;
  ctx.fillStyle = palette.paper;
  tracePolygon(ctx, polygon);
  ctx.fill();
}

function drawInk(ctx: Context, mark: InkMark, progress: number, palette: InkPalette) {
  if (progress >= 1 && mark.fillPolygon) knockOutFill(ctx, mark.fillPolygon, palette);
  const color = mark.color ?? palette.ink;
  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  let budget = progress >= 1 ? Infinity : progress * mark.length;
  for (const run of mark.runs) {
    if (budget < run.length) return drawRun(ctx, run, cutPolyline(run.points, budget), mark.weight, false);
    drawRun(ctx, run, run.points, mark.weight, true);
    budget -= run.length;
  }
}

function drawText(ctx: Context, mark: TextMark, progress: number, palette: InkPalette) {
  const visibleCharacters = progress >= 1 ? mark.text.length : Math.ceil(progress * mark.text.length);
  if (visibleCharacters <= 0) return;
  const color = mark.color ?? palette.ink;
  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  ctx.font = `500 ${mark.size}px ${palette.fontFamily}`;
  ctx.textAlign = "left";
  ctx.textBaseline = mark.baseline;
  const left = ALIGN_OFFSET[mark.align] * ctx.measureText(mark.text).width;
  const visible = mark.text.slice(0, visibleCharacters);
  ctx.save();
  ctx.translate(mark.x, mark.y);
  ctx.rotate(mark.rotation);
  ctx.globalAlpha = 0.06;
  ctx.lineWidth = Math.max(0.8, mark.size * 0.22);
  ctx.strokeText(visible, left, 0);
  ctx.globalAlpha = 0.27;
  ctx.lineWidth = Math.max(0.6, mark.size * 0.1);
  ctx.strokeText(visible, left, 0);
  ctx.globalAlpha = INK.bodyAlpha;
  ctx.fillText(visible, left, 0);
  ctx.restore();
}

function drawSpecks(ctx: Context, mark: SpeckMark, progress: number, palette: InkPalette) {
  ctx.fillStyle = palette.ink;
  const scale = progress >= 1 ? 1 : easeOutBack(progress);
  for (const speck of mark.specks) fillDisc(ctx, speck.x, speck.y, speck.radius * 2 * scale, speck.alpha);
}

function drawBlot(ctx: Context, mark: BlotMark, progress: number, palette: InkPalette) {
  const color = mark.color ?? palette.ink;
  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  const scale = progress >= 1 ? 1 : easeOutBack(progress);
  ctx.save();
  ctx.translate(mark.cx, mark.cy);
  ctx.scale(scale, scale);
  tracePolygon(ctx, mark.points.map(([x, y]) => [x - mark.cx, y - mark.cy] as const));
  ctx.globalAlpha = 1;
  ctx.fill();
  ctx.globalAlpha = 0.27;
  ctx.lineWidth = 2.2;
  ctx.stroke();
  ctx.restore();
}

function drawErase(ctx: Context, mark: EraseMark, progress: number) {
  if (progress < 1) return;
  ctx.save();
  ctx.globalCompositeOperation = "destination-out";
  ctx.globalAlpha = 1;
  tracePolygon(ctx, mark.points);
  ctx.fill();
  ctx.restore();
}

const DRAW_MARK: { [K in Mark["kind"]]: (ctx: Context, mark: Extract<Mark, { kind: K }>, progress: number, palette: InkPalette) => void } = {
  ink: drawInk,
  text: drawText,
  speck: drawSpecks,
  blot: drawBlot,
  erase: drawErase,
};

function drawMark(ctx: Context, mark: Mark, progress: number, palette: InkPalette) {
  (DRAW_MARK[mark.kind] as (ctx: Context, mark: Mark, progress: number, palette: InkPalette) => void)(ctx, mark, progress, palette);
}

export function markProgress(stamp: Stamp, mark: Mark, now: number) {
  if (now === Infinity) return 1;
  return clamp((now - stamp.startsAt - mark.start) / mark.duration, 0, 1);
}

/** Draws a stamp as far as the pen has got by `now`; pass Infinity to draw it finished. */
export function renderStamp(ctx: Context, stamp: Stamp, now: number, palette: InkPalette) {
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const mark of stamp.marks) {
    const progress = markProgress(stamp, mark, now);
    if (progress > 0) drawMark(ctx, mark, progress, palette);
  }
  ctx.globalAlpha = 1;
}
