"use client";

import { Html, Line } from "@react-three/drei";
import { Question } from "@phosphor-icons/react";
import { useMemo } from "react";
import { type Color, Vector3 } from "three";
import { type UncheckedThing, edgePositions } from "@/lib/room-changes";

/** A dotted box and a question for each thing only one video saw, shown when that video's surfaces are. */
function UncheckedMark({ thing, colour }: { thing: UncheckedThing; colour: Color }) {
  const points = useMemo(() => {
    const flat = edgePositions(thing.box.corners);
    return Array.from({ length: flat.length / 3 }, (_, i) => new Vector3(flat[3 * i], flat[3 * i + 1], flat[3 * i + 2]));
  }, [thing]);
  const { center, size } = thing.box;
  return (
    <group>
      <Line points={points} segments color={colour} lineWidth={1.5} dashed dashSize={0.03} gapSize={0.04} />
      <Html position={[center[0], center[1], center[2] + size[2] / 2 + 0.12]} center zIndexRange={[15, 0]}
        className="pointer-events-none">
        <span className="flex items-center gap-1 whitespace-nowrap rounded-full bg-sheet/95 py-1 pl-1.5 pr-2.5 text-sm text-ink shadow-float">
          <Question size={16} weight="bold" aria-hidden className="text-[var(--color-unseen)]" />
          <span className="hidden sm:inline">{thing.name}</span>
        </span>
      </Html>
    </group>
  );
}

export function UncheckedMarks({ things, colour, before, after }: {
  things: UncheckedThing[]; colour: Color; before: boolean; after: boolean;
}) {
  const shown = things.filter((thing) => (thing.video === "before" ? before : after));
  return <group>{shown.map((thing) => <UncheckedMark key={thing.id} thing={thing} colour={colour} />)}</group>;
}
