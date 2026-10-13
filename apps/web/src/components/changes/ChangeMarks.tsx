"use client";

import { Html, Line } from "@react-three/drei";
import { useMemo } from "react";
import { type Color, Quaternion, Vector3 } from "three";
import { Button } from "@/components/ui/Button";
import { type ChangePlace, type RoomChange, type Vec3, edgePositions, moveArc } from "@/lib/room-changes";
import type { CloudView } from "./ChangeCloud";
import { ChangeTypeIcon } from "./ChangeTypeIcon";

type MarkProps = {
  change: RoomChange;
  colour: Color;
  view: CloudView;
  selected: boolean;
  dimmed: boolean;
  /** Its card is the one being read, so the label spells the name out even on a phone. */
  reading: boolean;
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

/** A change's name over its box. On a phone only the change being read or picked spells its name out. */
function ChangeLabel({ change, place, selected, named, onSelect }: {
  change: RoomChange; place: ChangePlace; selected: boolean; named: boolean; onSelect: (id: string) => void;
}) {
  return (
    <Html position={topOf(place)} center zIndexRange={[20, 0]}>
      <Button variant="chip" aria-pressed={selected} aria-label={change.name} onClick={() => onSelect(change.id)}
        className={`change-tone-${change.type} py-1 pl-2`}>
        <ChangeTypeIcon type={change.type} />
        <span aria-hidden className={named ? "inline" : "hidden sm:inline"}>{change.name}</span>
      </Button>
    </Html>
  );
}

type Mode = "both" | "before" | "after";
type Side = "before" | "after";
/** For each mode and kind of change: the side drawn solid, the side drawn as a dashed ghost, and the arrow. */
type Drawing = { solid: Side | null; ghost: Side | null; arrow: boolean };

const DRAWINGS: Record<Mode, Record<RoomChange["type"], Drawing>> = {
  both: {
    moved: { solid: "after", ghost: "before", arrow: true },
    removed: { solid: null, ghost: "before", arrow: false },
    added: { solid: "after", ghost: null, arrow: false },
  },
  before: {
    moved: { solid: "before", ghost: null, arrow: false },
    removed: { solid: "before", ghost: null, arrow: false },
    added: { solid: null, ghost: "after", arrow: false },
  },
  after: {
    moved: { solid: "after", ghost: null, arrow: false },
    removed: { solid: null, ghost: "before", arrow: false },
    added: { solid: "after", ghost: null, arrow: false },
  },
};

function modeOf(view: CloudView): Mode {
  if (view.before && view.after) return "both";
  return view.before ? "before" : "after";
}

function markWidth(selected: boolean, dimmed: boolean): number {
  if (selected) return 3;
  return dimmed ? 1 : 2;
}

type PartProps = { change: RoomChange; side: Side | null; colour: Color; width: number };

function SideBox({ change, side, colour, width, dashed }: PartProps & { dashed: boolean }) {
  const place = side ? change[side] : null;
  if (!place) return null;
  return <BoxEdges place={place} colour={colour} dashed={dashed} width={width} />;
}

function Route({ change, colour, width }: Omit<PartProps, "side">) {
  if (!change.before || !change.after) return null;
  return <MoveArrow from={topOf(change.before)} to={topOf(change.after)} colour={colour} width={width} />;
}

/**
 * One change drawn in the room. Whatever the shown video has is drawn solid; a spot the shown
 * video has nothing at, such as a removed object seen with the after video, is a dashed ghost.
 */
export function ChangeMark({ change, colour, view, selected, dimmed, reading, onSelect }: MarkProps) {
  const drawing = DRAWINGS[modeOf(view)][change.type];
  const width = markWidth(selected, dimmed);
  const labelSide = drawing.solid ?? drawing.ghost;
  const place = labelSide ? change[labelSide] : null;
  return (
    <group>
      <SideBox change={change} side={drawing.solid} colour={colour} width={width} dashed={false} />
      <SideBox change={change} side={drawing.ghost} colour={colour} width={width} dashed />
      {drawing.arrow && <Route change={change} colour={colour} width={width} />}
      {place && <ChangeLabel change={change} place={place} selected={selected} named={selected || reading} onSelect={onSelect} />}
    </group>
  );
}
