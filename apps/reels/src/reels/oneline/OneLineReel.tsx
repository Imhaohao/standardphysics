import { useMemo } from "react";
import { useCurrentFrame } from "remotion";
import { cue, repeatCue, Soundtrack } from "../../components/Cues";
import { GlowDot } from "../../components/Glow";
import { InkLayer } from "../../components/InkLayer";
import { Grain, Paper, Vignette } from "../../components/Paper";
import { RevealLines } from "../../components/Type";
import { drawn, mix, progress, sweep } from "../../lib/ease";
import { inkDuration, type Point } from "../../lib/ink";
import { cumulativeLengths, fitPlan, onSheet, pointAtShare, smoothPath, type SheetFrame } from "../../lib/plan";
import { useFloorPlan, type FloorPlan } from "../../lib/scan";
import { FPS, toMs } from "../../lib/timing";
import { PaperModel } from "./PaperModel";
import { composeSheet, INK_ZOOM } from "./sheetInk";
import { TitleBlock } from "./TitleBlock";
import { TurningCircle } from "./TurningCircle";

const SHEET = { left: 110, top: 440, size: 860 } as const;
const SCAN = { name: "test1", minutes: 4 } as const;

export const ONE_LINE = {
  walkStart: 10,
  walkFrames: 180,
  tiltStart: 222,
  tiltFrames: 36,
  riseStart: 240,
  checkStart: 282,
  checkFrames: 96,
  flattenStart: 392,
  rewindStart: 424,
  rewindFrames: 44,
  length: 480,
} as const;

const WALK_MS = (ONE_LINE.walkFrames / FPS) * 1000;

type Sheet = { plan: FloorPlan; path: Point[]; frame: SheetFrame; stamps: ReturnType<typeof composeSheet>; inkEnd: number };

function useSheet(plan: FloorPlan | null): Sheet | null {
  return useMemo(() => {
    if (!plan) return null;
    const path = smoothPath(plan.path, 6);
    const frame = fitPlan(plan, { x: 40, y: 40, width: SHEET.size - 80, height: SHEET.size - 80 });
    const stamps = composeSheet({ plan, path, frame: { ...frame, offsetX: frame.offsetX, offsetY: frame.offsetY }, walkMs: WALK_MS });
    return { plan, path, frame, stamps, inkEnd: inkDuration(stamps) };
  }, [plan]);
}

const cues = [
  cue(ONE_LINE.walkStart, "scratch", 0.6),
  cue(ONE_LINE.walkStart + 110, "scratch", 0.6),
  cue(18, "tick", 0.5),
  cue(ONE_LINE.tiltStart, "whoosh", 0.6),
  ...repeatCue(ONE_LINE.riseStart, ONE_LINE.riseStart + 30, 2, "pop", 0.22),
  cue(ONE_LINE.checkStart, "scan", 0.7),
  cue(ONE_LINE.checkStart + 30, "scan", 0.5),
  cue(ONE_LINE.flattenStart, "whoosh-down", 0.5),
  cue(ONE_LINE.rewindStart, "whoosh", 0.5),
  cue(ONE_LINE.rewindStart + 4, "scratch", 0.35),
];

function inkTime(frame: number, inkEnd: number) {
  if (frame < ONE_LINE.walkStart) return 0;
  const forward = Math.min(inkEnd, toMs(frame - ONE_LINE.walkStart));
  const rewind = progress(frame, ONE_LINE.rewindStart, ONE_LINE.rewindFrames, sweep);
  return forward * (1 - rewind);
}

function sheetTransform(frame: number) {
  const tilt = progress(frame, ONE_LINE.tiltStart, ONE_LINE.tiltFrames, sweep) * (1 - progress(frame, ONE_LINE.flattenStart, 30, sweep));
  return { tilt, transform: `rotateX(${tilt * 54}deg) rotateZ(${tilt * -32}deg) scale(${1 - tilt * 0.12})` };
}

function riseOf(frame: number, count: number) {
  const falling = progress(frame, ONE_LINE.flattenStart - 8, 24, sweep);
  return (index: number) => progress(frame, ONE_LINE.riseStart + (index / count) * 30, 16, drawn) * (1 - falling);
}

function Captions() {
  return (
    <div className="absolute inset-x-safe-side top-safe-top">
      <RevealLines lines={["Walk a room once."]} at={18} exitAt={ONE_LINE.tiltStart - 16} className="reel-copy block text-title" />
      <div className="absolute inset-x-0 top-0">
        <RevealLines lines={["It stands up every", "table and chair."]} at={ONE_LINE.tiltStart + 10} exitAt={ONE_LINE.checkStart - 6} className="reel-copy block text-title" />
      </div>
      <div className="absolute inset-x-0 top-0">
        <RevealLines lines={["Then it checks where", "a wheelchair can turn."]} at={ONE_LINE.checkStart + 4} exitAt={ONE_LINE.flattenStart + 10} className="reel-copy block text-title" />
      </div>
    </div>
  );
}

function Pen({ sheet, frame }: { sheet: Sheet; frame: number }) {
  const walked = Math.min(1, inkTime(frame, sheet.inkEnd) / WALK_MS);
  const [x, y] = onSheet(sheet.frame, pointAtShare(sheet.path, walked));
  const shown = frame < ONE_LINE.walkStart + ONE_LINE.walkFrames + 6 || frame > ONE_LINE.rewindStart;
  return shown ? <GlowDot x={x} y={y} size={22} /> : null;
}

function checkRoute(path: Point[]) {
  const lengths = cumulativeLengths(path);
  const total = lengths[lengths.length - 1];
  return path.filter((_, index) => lengths[index] > total * 0.12 && lengths[index] < total * 0.62);
}

function SheetStage({ sheet }: { sheet: Sheet }) {
  const frame = useCurrentFrame();
  const { transform } = sheetTransform(frame);
  const route = useMemo(() => checkRoute(sheet.path), [sheet.path]);
  const checking = progress(frame, ONE_LINE.checkStart, ONE_LINE.checkFrames, (t) => mix(t, t * t * (3 - 2 * t), 0.6));
  const circleShown = progress(frame, ONE_LINE.checkStart - 4, 8) * (1 - progress(frame, ONE_LINE.flattenStart - 4, 10));
  return (
    <div className="absolute" style={{ left: SHEET.left, top: SHEET.top, width: SHEET.size, height: SHEET.size, perspective: 2400 }}>
      <div className="absolute inset-0" style={{ transformStyle: "preserve-3d", transform }}>
        <InkLayer stamps={sheet.stamps} timeMs={inkTime(frame, sheet.inkEnd)} width={SHEET.size} height={SHEET.size} zoom={INK_ZOOM} className="absolute inset-0" />
        <PaperModel objects={sheet.plan.objects} frame={sheet.frame} riseOf={riseOf(frame, sheet.plan.objects.length)} />
        {circleShown > 0 && <TurningCircle route={route} frame={sheet.frame} share={checking} size={SHEET.size} opacity={circleShown} />}
        <Pen sheet={sheet} frame={frame} />
      </div>
    </div>
  );
}

function walkedMetres(path: Point[]) {
  const lengths = cumulativeLengths(path);
  return Math.round(lengths[lengths.length - 1]);
}

export function OneLineReel() {
  const plan = useFloorPlan(SCAN.name);
  const sheet = useSheet(plan);
  return (
    <Paper>
      {sheet && <SheetStage sheet={sheet} />}
      <Captions />
      {plan && (
        <TitleBlock
          facts={[
            { label: "Walk", value: `${SCAN.minutes} min` },
            { label: "Path", value: `${walkedMetres(plan.path)} m` },
            { label: "Objects", value: String(plan.objects.length) },
          ]}
        />
      )}
      <Soundtrack bed="bed-oneline" bedVolume={0.5} cues={cues} loops />
      <Vignette strength={0.22} />
      <Grain strength={0.1} />
    </Paper>
  );
}
