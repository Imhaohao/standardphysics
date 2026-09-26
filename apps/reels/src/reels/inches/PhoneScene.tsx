import { useCurrentFrame } from "remotion";
import { Footage } from "../../components/Footage";
import { LidarRoom } from "../../components/LidarRoom";
import { ScanBar } from "../../components/ScanBar";
import { TapeLabel } from "../../components/Type";
import { progress, sweep } from "../../lib/ease";
import { REEL } from "../../lib/timing";

export const PHONE = { open: 14, firstTape: 12, secondTape: 44, sweepStart: 78, sweepEnd: 120 } as const;

function OpeningSlit({ frame }: { frame: number }) {
  const open = progress(frame, 0, PHONE.open, sweep);
  const edge = 0.5 * (1 - open);
  if (open >= 1) return null;
  return (
    <>
      <ScanBar at={edge} trail={0} />
      <ScanBar at={1 - edge} trail={0} />
    </>
  );
}

function footageClip(frame: number) {
  const open = progress(frame, 0, PHONE.open, sweep);
  const sweepAt = progress(frame, PHONE.sweepStart, PHONE.sweepEnd - PHONE.sweepStart, sweep);
  const halfHidden = 50 * (1 - open);
  return `inset(calc(${halfHidden}% + ${sweepAt * 100}%) 0 ${halfHidden}% 0)`;
}

export function PhoneScene() {
  const frame = useCurrentFrame();
  const sweepAt = progress(frame, PHONE.sweepStart, PHONE.sweepEnd - PHONE.sweepStart, sweep);
  const sweeping = frame >= PHONE.sweepStart && sweepAt < 1;
  const push = 1.04 + frame * 0.0012;
  return (
    <div className="absolute inset-0">
      {frame >= PHONE.sweepStart - 2 && (
        <div className="absolute inset-0 bg-night">
          <LidarRoom
            scan="test1"
            width={REEL.width}
            height={REEL.height}
            reveal={sweepAt}
            cutaway={2.3}
            radius={6.2}
            camera={{ azimuth: 0.35 + frame * 0.0045, elevation: 0.62 + sweepAt * 0.3, distance: 36 - sweepAt * 5 }}
          />
        </div>
      )}
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: footageClip(frame) }}>
        <Footage clip="phone-table" style={{ transform: `scale(${push})` }} />
      </div>
      <OpeningSlit frame={frame} />
      {sweeping && <ScanBar at={sweepAt} trail={0.12} />}
      <div className="absolute inset-x-safe-side top-safe-top flex flex-col items-start gap-6">
        <TapeLabel at={PHONE.firstTape} exitAt={PHONE.sweepStart + 20} className="reel-caption text-caption">
          A phone can catch it first.
        </TapeLabel>
        <TapeLabel at={PHONE.secondTape} exitAt={PHONE.sweepStart + 22} tilt={1.5} className="reel-caption text-caption">
          One walk measures the room.
        </TapeLabel>
      </div>
    </div>
  );
}
