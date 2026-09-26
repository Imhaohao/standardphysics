import { LIBRARY_POV_LENGTH, LibraryPov } from "./batch-a/LibraryPov";
import type { ReelSpec } from "./registry";

export const batchA: ReelSpec[] = [{ id: "LibraryPov", component: LibraryPov, durationInFrames: LIBRARY_POV_LENGTH }];
