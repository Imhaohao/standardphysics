import { DOLL_LENGTH, DollMeme } from "./batch-a/DollMeme";
import { LIBRARY_POV_LENGTH, LibraryPov } from "./batch-a/LibraryPov";
import { THERAPY_LENGTH, TherapyMeme } from "./batch-a/TherapyMeme";
import type { ReelSpec } from "./registry";

export const batchA: ReelSpec[] = [
  { id: "LibraryPov", component: LibraryPov, durationInFrames: LIBRARY_POV_LENGTH },
  { id: "TherapyMeme", component: TherapyMeme, durationInFrames: THERAPY_LENGTH },
  { id: "DollMeme", component: DollMeme, durationInFrames: DOLL_LENGTH },
];
