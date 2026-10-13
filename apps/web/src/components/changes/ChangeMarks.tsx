"use client";

import { Html, Line } from "@react-three/drei";
import { useMemo } from "react";
import { type Color, Quaternion, Vector3 } from "three";
import { type ChangePlace, type RoomChange, type Vec3, edgePositions, moveArc } from "@/lib/room-changes";
import type { CloudView } from "./ChangeCloud";
import { ChangeTypeIcon } from "./ChangeTypeIcon";

type MarkProps = {
  change: RoomChange;
  colour: Color;
  view: CloudView;
  selected: boolean;
  dimmed: boolean;
  onSelect: (id: string) => void;
};

function BoxEdges({ place, colour, dashed, width }: { place: ChangePlace; colour: Color; dashed: boolean; width: number }) {
  const points = useMemo(() => {
    const flat = edgePositions(place.box.corners);
    return Array.from({ length: flat.length / 3 }, (_, i) => new Vector3(flat[3 * i], flat[3 * i + 1], flat[3 * i + 2]));
  }, [place]);
  return <Line points={points} segments color={colour} lineWidth={width} dashed={dashed} dashSize={0.06} gapSize={0.05} />;
}

function MoveArrow({ from, to, colour, width }: { from: Vec3; to: Vec3; colour: Color; width: number }) {
  const arc = useMemo(() => moveArc(from, to).map((point) => new Vector3(...point)), [from, to]);
  const head = useMemo(() => {
    const tip = arc[arc.length - 1];
    const direction = tip.clone().sub(arc[arc.length - 4]).normalize();
    return { tip, rotation: new Quaternion().setFromUnitVectors(new Vector3(0, 1, 0), direction) };
  }, [arc]);
  return (
    <group>
      <Line points={arc} color={colour} lineWidth={width} />
      <mesh position={head.tip} quaternion={head.rotation}>
        <coneGeometry args={[0.05, 0.14, 16]} />
        <meshBasicMaterial color={colour} />
      </mesh>
    </group>
  );
}

function topOf(place: ChangePlace): Vec3 {
  const { center, size } = place.box;
  return [center[0], center[1], center[2] + size[2] / 2 + 0.12];
}

function ChangeLabel({ change, place, selected, onSelect }: {
  change: RoomChange; place: ChangePlace; selected: boolean; onSelect: (id: string) => void;
}) {
  return (
    <Html position={topOf(place)} center zIndexRange={[20, 0]}>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(change.id)}
        className={`change-tone-${change.type} pressable flex items-center gap-1.5 whitespace-nowrap rounded-full bg-sheet/95 py-1 pl-1.5 pr-3 text-sm font-medium text-ink shadow-float aria-pressed:bg-ink aria-pressed:text-paper`}
      >
        <ChangeTypeIcon type={change.type} />
        {change.name}
      </button>
    </Html>
  );
}

type PartProps = { change: RoomChange; colour: Color; view: CloudView; width: number };

function markWidth(selected: boolean, dimmed: boolean): number {
  if (selected) return 3;
  return dimmed ? 1 : 2;
}

/** Where the object was. Dashed once it is gone from view: a moved object's old spot, or a removed one beside the after video. */
function OldBox({ change, colour, view, width }: PartProps) {
  if (!change.before || !view.before) return null;
  const dashed = change.type !== "removed" || view.after;
  return <BoxEdges place={change.before} colour={colour} dashed={dashed} width={width} />;
}

function NewBox({ change, colour, view, width }: PartProps) {
  if (!change.after || !view.after) return null;
  return <BoxEdges place={change.after} colour={colour} dashed={false} width={width} />;
}

function Route({ change, colour, width }: PartProps) {
  if (change.type !== "moved" || !change.before || !change.after) return null;
  return <MoveArrow from={topOf(change.before)} to={topOf(change.after)} colour={colour} width={width} />;
}

function labelPlace(change: RoomChange, view: CloudView): ChangePlace | null {
  const preferred = view.after ? change.after : change.before;
  return preferred ?? change.after ?? change.before;
}

/** One change drawn in the room: its box, a ghost of where a moved object was, and the arrow between them. */
export function ChangeMark({ change, colour, view, selected, dimmed, onSelect }: MarkProps) {
  const parts = { change, colour, view, width: markWidth(selected, dimmed) };
  const place = labelPlace(change, view);
  return (
    <group>
      <OldBox {...parts} />
      <NewBox {...parts} />
      <Route {...parts} />
      {place && <ChangeLabel change={change} place={place} selected={selected} onSelect={onSelect} />}
    </group>
  );
}
