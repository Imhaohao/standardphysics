"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type ClearanceField, decodeClearance } from "@/lib/clearance-map";
import { type Checked, LayoutChecker, layoutKey } from "@/lib/layout-checker";
import { clearanceMap } from "@/lib/layout-client";
import type { MoveSet } from "@/lib/moves";
import { useStoredSwitch } from "@/lib/stored-switch";
import type { ClearanceMap, NodeMove } from "@/types/contracts";

/** The map last drawn and the layout it describes, or why there is none to draw. */
export type ClearanceView = { field: ClearanceField | null; key: string | null; failed: boolean };

const NOTHING_YET: ClearanceView = { field: null, key: null, failed: false };

/** Whether this viewer keeps the clearance map on, remembered in their browser like the other view choices. */
export function useClearanceChoice(): [boolean, (on: boolean) => void] {
  return useStoredSwitch("sp_clearance_map");
}

/**
 * The clearance map of the layout the plan last settled on, while the viewer has the map on.
 *
 * `settled` changes when the plan comes to rest, at the moments the layout check is asked for or answered from its
 * cache: a pause in a drag, a drop, an undo, a refused drop snapping back. One request is out at a time, a newer
 * layout replaces the one waiting, and a map already fetched comes back from the cache, the same way the checks are
 * asked for. Dragging never waits on any of it.
 */
export function useClearanceMap(scanId: string, revision: number, settled: MoveSet, on: boolean): ClearanceView {
  const [view, setView] = useState<ClearanceView>(NOTHING_YET);
  const wanted = useRef<string | null>(null);

  const fail = useCallback(() => setView((current) => ({ ...current, failed: true })), []);
  const show = useCallback((checked: Checked<ClearanceMap>) => {
    decodeClearance(checked.result)
      .then((field) => {
        if (wanted.current === checked.key) setView({ field, key: checked.key, failed: false });
      })
      .catch(fail);
  }, [fail]);

  const checker = useMapChecker(scanId, revision, show, fail);

  useEffect(() => {
    if (!on) return;
    wanted.current = layoutKey(settled);
    checker().request(settled);
  }, [on, settled, checker]);

  return view;
}

/** One checker per scan and revision, since a map fetched for one revision says nothing about the next. */
function useMapChecker(scanId: string, revision: number, onResult: (checked: Checked<ClearanceMap>) => void, onError: () => void) {
  const made = useRef<{ key: string; checker: LayoutChecker<ClearanceMap> } | null>(null);
  return useCallback(() => {
    const key = `${scanId}@${revision}`;
    if (made.current?.key === key) return made.current.checker;
    made.current?.checker.cancel();
    const run = (moves: NodeMove[], sequence: number) => clearanceMap(scanId, revision, sequence, moves);
    const fresh = new LayoutChecker<ClearanceMap>(run, { onResult, onError, onBusy: IGNORE_BUSY });
    made.current = { key, checker: fresh };
    return fresh;
  }, [scanId, revision, onResult, onError]);
}

const IGNORE_BUSY = () => {};

/** Whether the map on screen describes some other layout than the one shown, as it does mid-drag. */
export function isStale(view: ClearanceView, moves: MoveSet): boolean {
  return view.key !== layoutKey(moves);
}
