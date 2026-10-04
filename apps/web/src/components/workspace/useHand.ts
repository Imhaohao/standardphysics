"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { type HeldPiece, nudge, type Outcome, pickUp, pull, turn } from "@/lib/held-piece";
import { ruleBase } from "@/lib/layout-rules";
import type { MoveSet } from "@/lib/moves";
import type { Stop } from "@/lib/slide";
import type { SceneGraph } from "@/types/contracts";

const NOTHING_PRESSED: Stop[] = [];

function samePress(a: Stop[], b: Stop[]): boolean {
  return a.length === b.length && a.every((stop, index) => stop.nodeId === b[index].nodeId && stop.reason === b[index].reason);
}

/**
 * The piece in hand. A drag picks it up on its first move and the room is drawn
 * for it once; every later move slides it from where it is. Anything else that
 * changes the layout under it, like a refused drop snapping back, makes the next
 * move pick it up afresh. `pressedOn` is what it rests against right now.
 */
export function useHand(scene: SceneGraph) {
  const rules = useMemo(() => ruleBase(scene), [scene]);
  const held = useRef<{ piece: HeldPiece; placed: MoveSet } | null>(null);
  const [pressedOn, setPressedOn] = useState<Stop[]>(NOTHING_PRESSED);

  const press = useCallback((stops: Stop[]) => setPressedOn((current) => (samePress(current, stops) ? current : stops)), []);

  const pullBy = useCallback((moves: MoveSet, nodeId: string, dx: number, dy: number): MoveSet => {
    const arranging = { rules, base: scene, moves };
    const holding = held.current?.piece.nodeId === nodeId && held.current.placed === moves ? held.current.piece : pickUp(arranging, nodeId);
    const pulled = pull(arranging, holding, dx, dy);
    held.current = { piece: pulled.held, placed: pulled.moves };
    press(pulled.blockedBy);
    return pulled.moves;
  }, [rules, scene, press]);

  const letGo = useCallback(() => {
    held.current = null;
    press(NOTHING_PRESSED);
  }, [press]);

  /** A keyboard step or a turn button: a slide when it moves, a turn when it turns. */
  const step = useCallback((moves: MoveSet, nodeId: string, dx: number, dy: number, degrees: number): Outcome => {
    held.current = null;
    const arranging = { rules, base: scene, moves };
    return degrees !== 0 ? turn(arranging, nodeId, degrees) : nudge(arranging, nodeId, dx, dy);
  }, [rules, scene]);

  return { pressedOn, pullBy, letGo, step };
}
