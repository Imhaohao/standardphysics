import { useCurrentFrame } from "remotion";
import { Soundtrack, cue } from "../../components/Cues";
import { Grain, Paper, Vignette } from "../../components/Paper";
import { progress, sweep } from "../../lib/ease";
import { REEL } from "../../lib/timing";
import { OneShots, shot } from "./Sounds";
import { SonarRoom } from "./SonarRoom";

/** Nine seconds, which is exactly twelve beats of the scan bed, so picture and sound loop together. */
export const SATISFYING_SCAN = { revealEnd: 120, eraseStart: 150, eraseEnd: 262, length: 270 } as const;

const TRIANGLES_IN_SCAN = 988_079;
const RING_REACH_METRES = 6.5;
/** The loop opens mid-reveal, with the ring already sweeping, rather than on an empty frame. */
const OPENING_OFFSET = 55;
const counted = new Intl.NumberFormat("en-US");

const onScreen = (internal: number) => (internal - OPENING_OFFSET + SATISFYING_SCAN.length) % SATISFYING_SCAN.length;
const cues = [cue(onScreen(0), "scan", 0.7), cue(onScreen(SATISFYING_SCAN.eraseStart), "scan", 0.6), cue(onScreen(SATISFYING_SCAN.eraseStart + 4), "whoosh", 0.25)];
const shots = [shot(onScreen(SATISFYING_SCAN.revealEnd - 6), "c-chime", 0.5)];

function Counter({ frame }: { frame: number }) {
  const measured = progress(frame, 0, SATISFYING_SCAN.revealEnd, sweep);
  const erased = progress(frame, SATISFYING_SCAN.eraseStart, SATISFYING_SCAN.eraseEnd - SATISFYING_SCAN.eraseStart, sweep);
  const shown = measured * (1 - erased);
  return (
    <div className="absolute inset-x-safe-side top-safe-top text-paper-raised">
      <p className="reel-copy text-title">watching a phone measure a room</p>
      <p className="reel-copy figures mt-6 text-headline text-tape-light tape-glow" style={{ opacity: 0.35 + 0.65 * shown }}>
        {counted.format(Math.round(TRIANGLES_IN_SCAN * shown))}
      </p>
      <p className="reel-caption text-caption text-ink-faint">triangles of real LiDAR</p>
    </div>
  );
}

export function SatisfyingScan() {
  const frame = (useCurrentFrame() + OPENING_OFFSET) % SATISFYING_SCAN.length;
  const front = progress(frame, 0, SATISFYING_SCAN.revealEnd, sweep) * RING_REACH_METRES;
  const trailing = progress(frame, SATISFYING_SCAN.eraseStart, SATISFYING_SCAN.eraseEnd - SATISFYING_SCAN.eraseStart, sweep) * RING_REACH_METRES;
  const azimuth = 0.4 + (frame / SATISFYING_SCAN.length) * Math.PI * 2;
  return (
    <Paper tone="night">
      <div className="absolute inset-x-0 top-[380px] h-[1540px]">
        <SonarRoom scan="test1" width={REEL.width} height={1540} camera={{ azimuth, elevation: 0.95, distance: 38 }} front={front} trailing={trailing} cutaway={2.3} radius={6.4} />
      </div>
      <Counter frame={frame} />
      <Soundtrack bed="c-bed-scan" bedVolume={0.55} cues={cues} loops />
      <OneShots shots={shots} />
      <Vignette strength={0.45} />
      <Grain strength={0.08} />
    </Paper>
  );
}
