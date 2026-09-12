"use client";

import { Edges, useGLTF } from "@react-three/drei";
import { useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import { BoxGeometry, Matrix4, Mesh, type BufferGeometry } from "three";
import { displayMatrix, toViewerMatrix } from "@/lib/scene-matrix";
import type { SceneGraph, SceneNode } from "@/types/contracts";
import { MODEL, nodeColor, WALL_CUT_HEIGHT } from "./palette";

const UNIT_BOX = new BoxGeometry(1, 1, 1);
const HIDDEN_KINDS = new Set<SceneNode["kind"]>(["door", "window", "opening"]);

type Placed = { node: SceneNode; geometry: BufferGeometry; matrix: Matrix4 };

/** Walls stop at the cut height, like an architect's model, so the room reads from above. */
function cutWall(node: SceneNode, matrix: Matrix4): Matrix4 {
  if (node.kind !== "wall" || node.dimensions.z <= WALL_CUT_HEIGHT) return matrix;
  const base = node.transform.m[11] - node.dimensions.z / 2;
  const squash = new Matrix4()
    .makeTranslation(0, base, 0)
    .multiply(new Matrix4().makeScale(1, WALL_CUT_HEIGHT / node.dimensions.z, 1))
    .multiply(new Matrix4().makeTranslation(0, -base, 0));
  return squash.multiply(matrix);
}

function boxMatrix(node: SceneNode): Matrix4 {
  const scale = new Matrix4().makeScale(node.dimensions.x, node.dimensions.z, node.dimensions.y);
  return toViewerMatrix(node.transform).multiply(scale);
}

function placeFromGlb(meshes: Map<string, Mesh>, node: SceneNode, exported: SceneNode | undefined): Placed {
  const mesh = meshes.get(node.id);
  if (!mesh || !exported) return { node, geometry: UNIT_BOX, matrix: cutWall(node, boxMatrix(node)) };
  const matrix = displayMatrix(mesh.matrixWorld, exported.transform, node.transform);
  return { node, geometry: mesh.geometry, matrix: cutWall(node, matrix) };
}

function useGlbMeshes(url: string): Map<string, Mesh> {
  const { scene } = useGLTF(url);
  return useMemo(() => {
    scene.updateMatrixWorld(true);
    const found = new Map<string, Mesh>();
    scene.traverse((object) => {
      if (object instanceof Mesh) found.set(object.name, object);
    });
    return found;
  }, [scene]);
}

type ModelProps = {
  shown: SceneGraph;
  focus: Set<string> | null;
  focusColor: string;
  onSelectNode: (nodeId: string) => void;
};

function ModelNode({ placed, focus, focusColor, onSelectNode }: { placed: Placed } & Omit<ModelProps, "shown">) {
  const { node, geometry, matrix } = placed;
  const faded = focus !== null && !focus.has(node.id);
  const highlighted = focus?.has(node.id) ?? false;

  function select(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation();
    onSelectNode(node.id);
  }

  return (
    <mesh
      geometry={geometry}
      matrix={matrix}
      matrixAutoUpdate={false}
      castShadow={!faded && node.kind !== "floor"}
      receiveShadow
      onClick={faded ? undefined : select}
      raycast={faded ? () => null : undefined}
      name={node.id}
    >
      <meshStandardMaterial
        color={nodeColor(node)}
        roughness={0.92}
        transparent={faded}
        opacity={faded ? 0.15 : 1}
        depthWrite={!faded}
      />
      {highlighted && <Edges threshold={20} lineWidth={3} color={focusColor} renderOrder={5} />}
    </mesh>
  );
}

function ModelNodes({ placements, ...props }: { placements: Placed[] } & Omit<ModelProps, "shown">) {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => invalidate(), [placements, props.focus, invalidate]);
  return (
    <group>
      {placements.map((placed) => (
        <ModelNode key={placed.node.id} placed={placed} {...props} />
      ))}
    </group>
  );
}

function visibleNodes(scene: SceneGraph): SceneNode[] {
  return scene.nodes.filter((node) => !HIDDEN_KINDS.has(node.kind));
}

export function GlbShopModel({ url, exported, ...props }: ModelProps & { url: string; exported: SceneGraph }) {
  const meshes = useGlbMeshes(url);
  const placements = useMemo(() => {
    const exportedById = new Map(exported.nodes.map((node) => [node.id, node]));
    return visibleNodes(props.shown).map((node) => placeFromGlb(meshes, node, exportedById.get(node.id)));
  }, [meshes, exported, props.shown]);
  return <ModelNodes placements={placements} {...props} />;
}

export function BoxShopModel(props: ModelProps) {
  const placements = useMemo(
    () => visibleNodes(props.shown).map((node) => ({ node, geometry: UNIT_BOX, matrix: cutWall(node, boxMatrix(node)) })),
    [props.shown],
  );
  return <ModelNodes placements={placements} {...props} />;
}

export const MODEL_GROUND = MODEL.ground;
