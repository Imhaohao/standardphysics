import { useMemo } from "react";
import { useCurrentFrame } from "remotion";
import { cue, repeatCue, Soundtrack } from "../../../components/Cues";
import { GlowDot } from "../../../components/Glow";
import { InkLayer } from "../../../components/InkLayer";
import { Grain, Paper, Vignette } from "../../../components/Paper";
import { RevealLines } from "../../../components/Type";
import { drawn, progress, sweep } from "../../../lib/ease";
import { inkDuration, type Point } from "../../../lib/ink";
import { cumulativeLengths, fitPlan, onSheet, pointAtShare, smoothPath, type SheetFrame } from "../../../lib/plan";
import { useFloorPlan, type FloorPlan } from "../../../lib/scan";
import { FPS, toMs } from "../../../lib/timing";
import { PaperModel } from "../../oneline/PaperModel";
import { TitleBlock } from "../../oneline/TitleBlock";
import { BigTurningCircle } from "./BigTurningCircle";
import { composeFastSheet, FAST_INK_ZOOM } from "./fastSheetInk";

const SHEET = { left: 90, top: 470, size: 900 } as const;
const SCAN = { name: "test1", minutes: 4 } as const;

/** Twelve seconds, so the loop lands on the fast bed's own loop point. */
export const ONE_LINE_FAST = {
  walkFrames: 78,
  tiltStart: 84,
  tiltFrames: 22,
  riseStart: 92,
  checkStart: 116,
  checkFrames: 110,
  flattenStart: 250,
  rewindStart: 280,
  rewindFrames: 56,
  length: 360,
} as const;

const T = ONE_LINE_FAST;
const WALK_MS = (T.walkFrames / FPS) * 1000;

type Sheet = { plan: FloorPlan; path: Point[]; frame: SheetFrame; stamps: ReturnType<typeof composeFastSheet>; inkEnd: number };

function useSheet(plan: FloorPlan | null): Sheet | null {
  return useMemo(() => {
    if (!plan) return null;
    const path = smoothPath(plan.path, 6);
    const frame = fitPlan(plan, { x: 30, y: 30, width: SHEET.size - 60, height: SHEET.size - 60 });
    const stamps = composeFastSheet({ plan, path, frame, walkMs: WALK_MS });
    return { plan, path, frame, stamps, inkEnd: inkDuration(stamps) };
  }, [plan]);
}

const cues = [
  cue(0, "scratch", 0.7),
  cue(T.tiltStart, "whoosh", 0.6),
  ...repeatCue(T.riseStart, T.riseStart + 20, 2, "pop", 0.25),
  cue(T.checkStart, "scan", 0.7),
  cue(T.checkStart + 50, "scan", 0.5),
  cue(T.flattenStart, "whoosh-down", 0.5),
  cue(T.rewindStart, "whoosh", 0.5),
  cue(T.rewindStart + 4, "scratch", 0.4),
];

function inkTime(frame: number, inkEnd: number) {
  const forward = Math.min(inkEnd, toMs(frame));
  return forward * (1 - progress(frame, T.rewindStart, T.rewindFrames, sweep));
}

function sheetTransform(frame: number) {
  const tilt = progress(frame, T.tiltStart, T.tiltFrames, sweep) * (1 - progress(frame, T.flattenStart, 22, sweep));
  return `rotateX(${tilt * 54}deg) rotateZ(${tilt * -32}deg) scale(${1 - tilt * 0.1})`;
}

function riseOf(frame: number, count: number) {
  const falling = progress(frame, T.flattenStart - 6, 18, sweep);
  return (index: number) => progress(frame, T.riseStart + (index / count) * 18, 12, drawn) * (1 - falling);
}

function Captions() {
  const frame = useCurrentFrame();
  const returning = frame >= T.rewindStart;
  return (
    <div className="absolute inset-x-safe-side top-safe-top">
      {returning ? (
        <RevealLines lines={["Walk a room", "once."]} at={T.rewindStart + 30} className="reel-copy block text-headline" />
      ) : (
        <RevealLines lines={["Walk a room", "once."]} at={-40} exitAt={T.tiltStart - 6} className="reel-copy block text-headline" />
      )}
      <div className="absolute inset-x-0 top-0">
        <RevealLines lines={["It stands up every", "table and chair."]} at={T.tiltStart + 2} exitAt={T.checkStart - 4} className="reel-copy block text-title" />
      </div>
      <div className="absolute inset-x-0 top-0">
        <RevealLines lines={["Then it checks where", "a wheelchair can turn."]} at={T.checkStart + 2} exitAt={T.flattenStart + 4} className="reel-copy block text-title" />
      </div>
    </div>
  );
}

function checkRoute(path: Point[]) {
  const lengths = cumulativeLengths(path);
  const total = lengths[lengths.length - 1];
  return path.filter((_, index) => lengths[index] > total * 0.12 && lengths[index] < total * 0.62);
}

function Pen({ sheet, frame }: { sheet: Sheet; frame: number }) {
  const walked = Math.min(1, inkTime(frame, sheet.inkEnd) / WALK_MS);
  const [x, y] = onSheet(sheet.frame, pointAtShare(sheet.path, walked));
  const shown = frame < T.walkFrames + 4 || frame > T.rewindStart;
  return shown ? <GlowDot x={x} y={y} size={26} /> : null;
}

function SheetStage({ sheet }: { sheet: Sheet }) {
  const frame = useCurrentFrame();
  const route = useMemo(() => checkRoute(sheet.path), [sheet.path]);
  const checking = progress(frame, T.checkStart, T.checkFrames, (t) => t * t * (3 - 2 * t));
  const circleShown = progress(frame, T.checkStart - 4, 8) * (1 - progress(frame, T.flattenStart - 4, 10));
  return (
    <div className="absolute" style={{ left: SHEET.left, top: SHEET.top, width: SHEET.size, height: SHEET.size, perspective: 2400 }}>
      <div className="absolute inset-0" style={{ transformStyle: "preserve-3d", transform: sheetTransform(frame) }}>
        <InkLayer stamps={sheet.stamps} timeMs={inkTime(frame, sheet.inkEnd)} width={SHEET.size} height={SHEET.size} zoom={FAST_INK_ZOOM} className="absolute inset-0" />
        <PaperModel objects={sheet.plan.objects} frame={sheet.frame} riseOf={riseOf(frame, sheet.plan.objects.length)} />
        {circleShown > 0 && <BigTurningCircle route={route} frame={sheet.frame} share={checking} size={SHEET.size} opacity={circleShown} />}
        <Pen sheet={sheet} frame={frame} />
      </div>
    </div>
  );
}

function walkedMetres(path: Point[]) {
  const lengths = cumulativeLengths(path);
  return Math.round(lengths[lengths.length - 1]);
}

/** The one-line reel, fast: the room inks itself in two and a half seconds, stands up, gets checked, and rewinds into a loop. */
export function OneLineFast() {
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
      <Soundtrack bed="c-bed-fastline" bedVolume={0.5} cues={cues} loops />
      <Vignette strength={0.22} />
      <Grain strength={0.1} />
    </Paper>
  );
}
