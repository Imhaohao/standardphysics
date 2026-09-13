"use client";

import { Html, Line } from "@react-three/drei";
import { useMemo } from "react";
import { Color, DoubleSide, Shape, Vector2, Vector3 } from "three";
import { toViewer } from "@/lib/coordinates";
import type { Focus } from "@/lib/findings";
import type { Locus } from "@/types/contracts";
import { MODEL, outcomeColor } from "./palette";

const LIFT = 0.012;

function viewerPoints(locus: Locus): Vector3[] {
  return locus.annotation.points.map((point) => new Vector3(...toViewer(point)).add(new Vector3(0, LIFT, 0)));
}

function MeasurementLabel({ position, text, color }: { position: Vector3; text: string; color: string }) {
  return (
    <Html position={position} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
      <span
        className="measurement block whitespace-nowrap rounded-md bg-ink px-2.5 py-1 text-lg font-bold text-paper shadow-lg"
        style={{ boxShadow: `0 0 0 2px ${color}, 0 6px 18px rgb(27 28 30 / 0.25)` }}
      >
        {text}
      </span>
    </Html>
  );
}

function endTicks(start: Vector3, end: Vector3): Vector3[][] {
  const along = end.clone().sub(start).setY(0).normalize();
  const across = new Vector3(-along.z, 0, along.x).multiplyScalar(0.09);
  return [start, end].map((point) => [point.clone().add(across), point.clone().sub(across)]);
}

function DimensionLine({ locus, color }: { locus: Locus; color: string }) {
  const [start, end] = viewerPoints(locus);
  const middle = start.clone().lerp(end, 0.5).add(new Vector3(0, 0.42, 0));
  return (
    <group>
      <Line points={[start, end]} color={color} lineWidth={4} depthTest={false} renderOrder={10} />
      {endTicks(start, end).map((tick, index) => (
        <Line key={index} points={tick} color={color} lineWidth={4} depthTest={false} renderOrder={10} />
      ))}
      <MeasurementLabel position={middle} text={locus.annotation.label} color={color} />
    </group>
  );
}

function Region({ locus, color }: { locus: Locus; color: string }) {
  const points = viewerPoints(locus);
  const shape = useMemo(() => new Shape(points.map((p) => new Vector2(p.x, -p.z))), [points]);
  const height = points[0]?.y ?? LIFT;
  const centre = points.reduce((sum, p) => sum.add(p), new Vector3()).multiplyScalar(1 / points.length);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position-y={height} renderOrder={9}>
        <shapeGeometry args={[shape]} />
        <meshBasicMaterial color={color} transparent opacity={0.22} side={DoubleSide} depthWrite={false} />
      </mesh>
      <Line points={[...points, points[0]]} color={color} lineWidth={3} depthTest={false} />
      <MeasurementLabel position={centre.add(new Vector3(0, 0.25, 0))} text={locus.annotation.label} color={color} />
    </group>
  );
}

function clearanceColor(inches: number | null | undefined, required: number | null): string {
  if (inches === null || inches === undefined) return "#b9b5ab";
  return required !== null && inches < required ? MODEL.problem : MODEL.pass;
}

function Path({ locus, required }: { locus: Locus; required: number | null }) {
  const points = viewerPoints(locus);
  const colors = points.map((_, index) => clearanceColor(locus.annotation.point_inches?.[index], required));
  return <Line points={points} vertexColors={colors.map((c) => new Color(c))} lineWidth={5} depthTest={false} />;
}

export function FindingAnnotation({ finding }: { finding: Focus }) {
  const locus = finding.locus;
  if (!locus) return null;
  const color = outcomeColor(finding.outcome);
  if (locus.annotation.kind === "dimension_line") return <DimensionLine locus={locus} color={color} />;
  if (locus.annotation.kind === "region") return <Region locus={locus} color={color} />;
  return <Path locus={locus} required={finding.required_inches} />;
}
