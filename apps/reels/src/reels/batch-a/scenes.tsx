import type { ReactNode } from "react";
import { useCurrentFrame } from "remotion";
import { LidarRoom } from "../../components/LidarRoom";
import { Shot } from "../../components/Shot";
import { progress, sweep } from "../../lib/ease";
import { REEL } from "../../lib/timing";

/** Phone-in-hand footage that pushes into the screen and goes dark, ready to cut to the model. */
export function PhoneDive({ clip, diveAt, children }: { clip: string; diveAt: number; children?: ReactNode }) {
  const frame = useCurrentFrame();
  const dive = progress(frame, diveAt, 24, (t) => t * t * t);
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0" style={{ transform: `scale(${1 + dive * 5})`, transformOrigin: "42% 55%" }}>
        <Shot clip={clip} />
      </div>
      <div className="absolute inset-0 bg-night" style={{ opacity: progress(frame, diveAt + 18, 6) }} />
      {children}
    </div>
  );
}

type ModelSweepProps = { children?: ReactNode; spin?: number; startReveal?: number; radius?: number };

/** The test1 LiDAR room on black, measured into view by the scan front and turning slowly. */
export function ModelSweep({ children, spin = 0.006, startReveal = 0.5, radius = 6.2 }: ModelSweepProps) {
  const frame = useCurrentFrame();
  const reveal = startReveal + (1 - startReveal) * progress(frame, 0, 34, sweep);
  return (
    <div className="absolute inset-0 bg-night">
      <LidarRoom
        scan="test1"
        width={REEL.width}
        height={REEL.height}
        reveal={reveal}
        cutaway={2.3}
        radius={radius}
        camera={{ azimuth: -0.5 + frame * spin, elevation: 0.6 + reveal * 0.3, distance: 33 - reveal * 3 }}
      />
      {children}
    </div>
  );
}
