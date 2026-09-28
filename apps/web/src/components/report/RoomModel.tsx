"use client";

import { OrbitControls, OrthographicCamera } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useMemo, useState } from "react";
import { BoxGeometry, Color, EdgesGeometry, Matrix4, Plane, Vector3 } from "three";
import { toViewerMatrix } from "@/lib/scene-matrix";
import type { SceneGraph, SceneNode } from "@/types/contracts";

/** The height an architect's plan is cut at, so the room reads from above without its walls in the way. */
const SECTION_CUT_METERS = 48 * 0.0254;
/** A sheet the scan measured with no thickness still needs a sliver to catch light on screen. */
const SHEET_METERS = 0.02;
const UNIT_BOX = new BoxGeometry(1, 1, 1);
const UNIT_EDGES = new EdgesGeometry(UNIT_BOX);

interface ModelColors {
  clay: string;
  ink: string;
  accent: string;
}

function readColors(): ModelColors {
  const styles = getComputedStyle(document.documentElement);
  const token = (name: string) => styles.getPropertyValue(name).trim();
  return { clay: token("--color-sheet"), ink: token("--color-ink"), accent: token("--color-accent") };
}

function boxMatrix(node: SceneNode): Matrix4 {
  const { x, y, z } = node.dimensions;
  const scale = new Matrix4().makeScale(Math.max(x, SHEET_METERS), Math.max(z, SHEET_METERS), Math.max(y, SHEET_METERS));
  return toViewerMatrix(node.transform).multiply(scale);
}

function roomExtent(scene: SceneGraph) {
  const xs = scene.nodes.map((node) => node.transform.m[3]);
  const ys = scene.nodes.map((node) => node.transform.m[7]);
  const floor = Math.min(...scene.nodes.map((node) => node.transform.m[11] - node.dimensions.z / 2));
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  return { center: new Vector3((minX + maxX) / 2, floor, -(minY + maxY) / 2), span: Math.max(maxX - minX, maxY - minY, 1), floor };
}

function Piece({ node, color, edge, clip }: { node: SceneNode; color: string; edge: string; clip: Plane[] }) {
  const matrix = useMemo(() => boxMatrix(node), [node]);
  return (
    <group matrix={matrix} matrixAutoUpdate={false}>
      <mesh geometry={UNIT_BOX}>
        <meshStandardMaterial color={color} roughness={0.9} clippingPlanes={clip} clipShadows />
      </mesh>
      <lineSegments geometry={UNIT_EDGES}>
        <lineBasicMaterial color={edge} clippingPlanes={clip} />
      </lineSegments>
    </group>
  );
}

function Ghost({ node, color, clip }: { node: SceneNode; color: string; clip: Plane[] }) {
  const matrix = useMemo(() => boxMatrix(node), [node]);
  return (
    <lineSegments geometry={UNIT_EDGES} matrix={matrix} matrixAutoUpdate={false}>
      <lineBasicMaterial color={color} transparent opacity={0.55} clippingPlanes={clip} />
    </lineSegments>
  );
}

function FittedCamera({ span }: { span: number }) {
  const size = useThree((state) => state.size);
  return (
    <OrthographicCamera
      makeDefault
      position={[span * 1.4, span * 1.3, span * 1.4]}
      near={-span * 10}
      far={span * 10}
      zoom={Math.min(size.width, size.height) / (span * 0.95)}
    />
  );
}

interface RoomModelProps {
  scene: SceneGraph;
  moved: ReadonlySet<string>;
  /** The pieces as they stood before a plan moved them, outlined where they were. */
  ghosts: SceneNode[];
  turning: boolean;
}

export default function RoomModel({ scene, moved, ghosts, turning }: RoomModelProps) {
  const [colors] = useState(readColors);
  const { center, span, floor } = useMemo(() => roomExtent(scene), [scene]);
  const clip = useMemo(() => [new Plane(new Vector3(0, -1, 0), floor + SECTION_CUT_METERS)], [floor]);
  const background = useMemo(() => new Color(colors.clay), [colors.clay]);
  return (
    <Canvas
      frameloop={turning ? "always" : "demand"}
      onCreated={({ gl, scene: three }) => {
        gl.localClippingEnabled = true;
        three.background = background;
      }}
      dpr={[1, 2]}
    >
      <FittedCamera span={span} />
      <ambientLight intensity={1.6} />
      <directionalLight position={[-4, 10, 6]} intensity={1.8} />
      <group position={[-center.x, -center.y, -center.z]}>
        {scene.nodes.map((node) => (
          <Piece key={node.id} node={node} color={moved.has(node.id) ? colors.accent : colors.clay} edge={colors.ink} clip={clip} />
        ))}
        {ghosts.map((node) => <Ghost key={node.id} node={node} color={colors.accent} clip={clip} />)}
      </group>
      <OrbitControls enablePan={false} enableZoom={false} autoRotate={turning} autoRotateSpeed={0.5} target={[0, 0, 0]} />
    </Canvas>
  );
}
