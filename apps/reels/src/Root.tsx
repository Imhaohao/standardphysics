import "./theme.css";
import "./fonts";
import { Composition } from "remotion";
import { FPS, REEL } from "./lib/timing";
import { INCHES_DURATION, InchesReel } from "./reels/inches/InchesReel";
import { POV_DURATION, PovReel } from "./reels/pov/PovReel";
import { ONE_LINE, OneLineReel } from "./reels/oneline/OneLineReel";

export function Root() {
  return (
    <>
      <Composition id="Inches" component={InchesReel} durationInFrames={INCHES_DURATION} fps={FPS} width={REEL.width} height={REEL.height} />
      <Composition id="Pov" component={PovReel} durationInFrames={POV_DURATION} fps={FPS} width={REEL.width} height={REEL.height} />
      <Composition id="OneLine" component={OneLineReel} durationInFrames={ONE_LINE.length} fps={FPS} width={REEL.width} height={REEL.height} />
    </>
  );
}
