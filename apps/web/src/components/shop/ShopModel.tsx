"use client";

import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type ComponentRef } from "react";
import {
  BoxGeometry,
  CylinderGeometry,
  EdgesGeometry,
  Group,
  LineBasicMaterial,
  Material,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Plane,
  ShadowMaterial,
  Vector3,
} from "three";
import type { ThemeColors } from "@/lib/themeColors";
import { placeCardReader } from "./counterLayout";
import { doorSwings, shopPieces, type PartFinish, type PieceRole, type ShopPiece } from "./shopParts";
import { useStageLevels } from "./stageLevels";
import { sweepFrontZ } from "./sweep";
import type { StageLevels } from "./shots";

type MaterialGroup = "context" | "finding";
type FinishMaterials = Record<PartFinish, MeshStandardMaterial | MeshBasicMaterial>;

const materialGroupByRole: Record<PieceRole, MaterialGroup> = {
  context: "context",
  counter: "finding",
  cardReader: "finding",
};

const baseOpacityByFinish: Record<PartFinish, number> = { clay: 1, floor: 1, ink: 1, glass: 0.55 };
const focusDimByFinish: Record<PartFinish, number> = { clay: 0.85, floor: 0.3, ink: 0.85, glass: 0.9 };
const EDGE_OPACITY = 0.5;

function createFinishMaterials(colors: ThemeColors, clippingPlanes: Plane[]): FinishMaterials {
  const shared = { clippingPlanes, clipShadows: true, transparent: true };
  return {
    clay: new MeshStandardMaterial({ ...shared, color: colors.clay, roughness: 0.92 }),
    floor: new MeshStandardMaterial({ ...shared, color: colors.floor, roughness: 1 }),
    glass: new MeshStandardMaterial({ ...shared, color: colors.glass, roughness: 0.15, depthWrite: false }),
    ink: new MeshBasicMaterial({ ...shared, color: colors.ink }),
  };
}

function useShopMaterials(colors: ThemeColors) {
  return useMemo(() => {
    const clipPlane = new Plane(new Vector3(0, 0, 1), 0);
    const clippingPlanes = [clipPlane];
    const edgeSettings = { clippingPlanes, transparent: true, color: colors.ink, opacity: EDGE_OPACITY };
    return {
      clipPlane,
      surfaces: {
        context: createFinishMaterials(colors, clippingPlanes),
        finding: createFinishMaterials(colors, clippingPlanes),
      } satisfies Record<MaterialGroup, FinishMaterials>,
      edges: {
        context: new LineBasicMaterial(edgeSettings),
        finding: new LineBasicMaterial(edgeSettings),
      } satisfies Record<MaterialGroup, LineBasicMaterial>,
      shadowCatcher: new ShadowMaterial({ opacity: 0.2, transparent: true }),
    };
  }, [colors]);
}

function setOpacity(material: Material, opacity: number) {
  material.opacity = opacity;
  material.visible = opacity > 0.002;
}

function contextOpacity(levels: StageLevels, finish: PartFinish) {
  return levels.presence * baseOpacityByFinish[finish] * (1 - focusDimByFinish[finish] * levels.focusOnCounter);
}

const unitBox = new BoxGeometry(1, 1, 1);
const unitCylinder = new CylinderGeometry(0.5, 0.5, 1, 28);
const geometries = { box: unitBox, cylinder: unitCylinder };
const edgeGeometries = { box: new EdgesGeometry(unitBox), cylinder: new EdgesGeometry(unitCylinder, 40) };

type ShopMaterials = ReturnType<typeof useShopMaterials>;

function PieceParts({ piece, materials }: { piece: ShopPiece; materials: ShopMaterials }) {
  const group = materialGroupByRole[piece.role];
  return piece.parts.map((shopPart, index) => (
    <group key={index} position={shopPart.center} scale={shopPart.size}>
      <mesh
        geometry={geometries[shopPart.shape]}
        material={materials.surfaces[group][shopPart.finish]}
        castShadow={shopPart.finish !== "glass"}
        receiveShadow
      />
      {shopPart.finish !== "ink" && (
        <lineSegments geometry={edgeGeometries[shopPart.shape]} material={materials.edges[group]} />
      )}
    </group>
  ));
}

function StaticPiece({ piece, materials }: { piece: ShopPiece; materials: ShopMaterials }) {
  return (
    <group position={piece.position} quaternion={piece.quaternion}>
      <PieceParts piece={piece} materials={materials} />
    </group>
  );
}

function CardReaderPiece({ piece, materials }: { piece: ShopPiece; materials: ShopMaterials }) {
  const levels = useStageLevels();
  const ref = useRef<Group>(null);

  useFrame(() => {
    if (!ref.current) return;
    placeCardReader(ref.current.position, levels.readerMoved);
  });

  return (
    <group ref={ref} position={piece.position} quaternion={piece.quaternion}>
      <PieceParts piece={piece} materials={materials} />
    </group>
  );
}

function DoorSwing({ hinge, width, color }: { hinge: Vector3; width: number; color: ThemeColors["ink"] }) {
  const levels = useStageLevels();
  const arc = useRef<ComponentRef<typeof Line>>(null);
  const points = useMemo(
    () =>
      Array.from({ length: 33 }, (_, step) => {
        const angle = (step / 32) * (Math.PI / 2);
        return new Vector3(hinge.x + Math.cos(angle) * width, hinge.y, hinge.z - Math.sin(angle) * width);
      }),
    [hinge, width],
  );

  useFrame(() => {
    if (!arc.current) return;
    setOpacity(arc.current.material, levels.solidified * contextOpacity(levels, "clay") * 0.6);
  });

  return (
    <Line
      ref={arc}
      points={[new Vector3(hinge.x, hinge.y, hinge.z - width), hinge, ...points]}
      color={color}
      lineWidth={1.25}
      transparent
    />
  );
}

export function ShopModel({ colors }: { colors: ThemeColors }) {
  const levels = useStageLevels();
  const materials = useShopMaterials(colors);
  const root = useRef<Group>(null);

  useFrame(() => {
    if (!root.current) return;
    materials.clipPlane.set(new Vector3(0, 0, 1), -sweepFrontZ(levels.solidified));
    materials.clipPlane.applyMatrix4(root.current.matrixWorld);

    for (const finish of Object.keys(baseOpacityByFinish) as PartFinish[]) {
      setOpacity(materials.surfaces.context[finish], contextOpacity(levels, finish));
      setOpacity(materials.surfaces.finding[finish], levels.presence * baseOpacityByFinish[finish]);
    }

    const highlight = levels.focusOnCounter * levels.measuring;
    setOpacity(materials.edges.context, levels.presence * EDGE_OPACITY * (1 - 0.8 * levels.focusOnCounter));
    setOpacity(materials.edges.finding, levels.presence * (EDGE_OPACITY + 0.5 * highlight));
    materials.edges.finding.color.copy(colors.ink).lerp(colors.fail, highlight * (1 - levels.readerMoved));
    setOpacity(materials.shadowCatcher, levels.presence * levels.solidified * 0.22);
  });

  return (
    <group ref={root}>
      {shopPieces.map((piece) =>
        piece.role === "cardReader" ? (
          <CardReaderPiece key={piece.key} piece={piece} materials={materials} />
        ) : (
          <StaticPiece key={piece.key} piece={piece} materials={materials} />
        ),
      )}
      {doorSwings.map((swing) => (
        <DoorSwing key={swing.key} hinge={swing.hinge} width={swing.width} color={colors.ink} />
      ))}
      <mesh rotation-x={-Math.PI / 2} position-y={-0.141} material={materials.shadowCatcher} receiveShadow>
        <planeGeometry args={[40, 40]} />
      </mesh>
    </group>
  );
}
