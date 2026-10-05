"use client";

import { useMemo } from "react";
import type { Arrangement } from "@/components/workspace/useArrangement";
import { useWideScreen } from "@/lib/wide-screen";
import type { ClearanceBands, SceneGraph } from "@/types/contracts";
import { LEGEND_INSET_PX } from "./ClearanceKey";
import type { ClearanceOverlay } from "./ClearancePlan";
import { isStale, useClearanceChoice, useClearanceMap } from "./useClearanceMap";
import { useClearancePicture, usePictureUrl } from "./useClearancePicture";

export type ClearanceControls = {
  /** Whether the viewer has the map on, which the toggle shows even where the map can't be drawn. */
  on: boolean;
  setOn: (on: boolean) => void;
  overlay: ClearanceOverlay | null;
  bands: ClearanceBands | null;
  failed: boolean;
  /** How far the model's picture slides, so the shop centres in the part the legend leaves uncovered. */
  frameShift: number;
};

/**
 * Everything a view needs to offer the clearance map: the viewer's remembered choice, and, while it is on and the
 * view shows the arrangement's layout, the map of that layout ready to draw.
 */
export function useClearanceOverlay(scene: SceneGraph, arrangement: Arrangement, available: boolean): ClearanceControls {
  const [chosen, setOn] = useClearanceChoice();
  const on = chosen && available;
  const view = useClearanceMap(scene.scan_id, scene.revision, arrangement.settled, on);
  const picture = useClearancePicture(on ? view.field : null);
  const url = usePictureUrl(picture);
  const stale = isStale(view, arrangement.moves);
  const overlay = useMemo(() => (picture ? { picture, url, stale } : null), [picture, url, stale]);
  const wide = useWideScreen();
  const frameShift = on && wide ? -LEGEND_INSET_PX / 2 : 0;
  return { on: chosen, setOn, overlay, bands: view.field?.bands ?? null, failed: on && view.failed, frameShift };
}
