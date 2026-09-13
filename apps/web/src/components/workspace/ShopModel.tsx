"use client";

import { Edges, Html, useGLTF } from "@react-three/drei";
import { useThree, type ThreeEvent } from "@react-three/fiber";
import { Lock } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { BoxGeometry, Matrix4, Mesh, MeshStandardMaterial, Plane, Raycaster, Vector3, type BufferGeometry, type Intersection, type Material } from "three";
import { canUseCapturedGlbGeometry, displayScale } from "@/lib/display-geometry";
import { displayMatrix, toViewerMatrix } from "@/lib/scene-matrix";
import type { SceneGraph, SceneNode } from "@/types/contracts";
import { MODEL, nodeColor, WALL_CUT_HEIGHT } from "./palette";

const UNIT_BOX = new BoxGeometry(1, 1, 1);
/** Viewer supplies one stable ground plane; RoomPlan floors are often rotated zero-depth shells. */
const HIDDEN_KINDS = new Set<SceneNode["kind"]>(["door", "window", "opening"]);
const WALL_CLIP_PLANE = new Plane(new Vector3(0, -1, 0), WALL_CUT_HEIGHT);

type Placed = { node: SceneNode; geometry: BufferGeometry; matrix: Matrix4; sourceMaterial: Material | Material[] | null };

export type ArrangeHandlers = {
  activeId: string | null;
  blockedIds: Set<string>;
  onGrab: (nodeId: string) => void;
  onDrag: (nodeId: string, dx: number, dy: number) => void;
  onDrop: (nodeId: string) => void;
};

function boxMatrix(node: SceneNode): Matrix4 {
  const scale = new Matrix4().makeScale(...displayScale(node));
  return toViewerMatrix(node.transform).multiply(scale);
}

// eslint-disable-next-line complexity
function placeFromGlb(meshes: Map<string, Mesh>, node: SceneNode, exported: SceneNode | undefined, stale: boolean): Placed | null {
  const mesh = meshes.get(node.id);
  // RoomPlan floor shells can have a zero axis. Only draw a floor when the GLB
  // supplies real triangles; a unit-box fallback would make a black slab.
  if ((!mesh || !exported) && node.kind === "floor") return null;
  if (!mesh || !exported) return { node, geometry: UNIT_BOX, matrix: boxMatrix(node), sourceMaterial: null };
  const matrix = displayMatrix(mesh.matrixWorld, exported.transform, node.transform);
  if (!canUseCapturedGlbGeometry(node, mesh.geometry, matrix, stale)) {
    if (node.kind === "floor" && !stale) return null;
    return { node, geometry: UNIT_BOX, matrix: boxMatrix(node), sourceMaterial: null };
  }
  return { node, geometry: mesh.geometry, matrix, sourceMaterial: mesh.material };
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
  arrange: ArrangeHandlers | null;
  cutWalls?: boolean;
  materialMode?: "captured" | "plain" | "coverage";
  staleNodeIds?: Set<string>;
  coverage?: Map<string, number>;
};

/** A level plane at the height the piece was grabbed, so it stays under the pointer instead of the floor below it. */
function grabPlane(event: ThreeEvent<PointerEvent>): Plane {
  return new Plane(new Vector3(0, 1, 0), -event.point.y);
}

function planeHit(event: ThreeEvent<PointerEvent>, plane: Plane): Vector3 | null {
  return event.ray.intersectPlane(plane, new Vector3());
}

function setCursor(cursor: string) {
  document.body.style.cursor = cursor;
}

function useDrag(node: SceneNode, arrange: ArrangeHandlers | null) {
  const from = useRef<Vector3 | null>(null);
  const plane = useRef<Plane | null>(null);
  if (!arrange || !node.movable || node.kind !== "object") return {};
  return {
    onPointerDown(event: ThreeEvent<PointerEvent>) {
      event.stopPropagation();
      (event.target as unknown as Element).setPointerCapture(event.pointerId);
      plane.current = grabPlane(event);
      from.current = planeHit(event, plane.current);
      arrange.onGrab(node.id);
      setCursor("grabbing");
    },
    onPointerMove(event: ThreeEvent<PointerEvent>) {
      const hit = from.current && plane.current && planeHit(event, plane.current);
      if (!from.current || !hit) return;
      arrange.onDrag(node.id, hit.x - from.current.x, -(hit.z - from.current.z));
      from.current = hit;
    },
    onPointerUp(event: ThreeEvent<PointerEvent>) {
      if (!from.current) return;
      (event.target as unknown as Element).releasePointerCapture(event.pointerId);
      from.current = null;
      arrange.onDrop(node.id);
      setCursor("grab");
    },
  };
}

function edgeColor(node: SceneNode, props: Omit<ModelProps, "shown">): string | null {
  if (props.arrange?.blockedIds.has(node.id)) return MODEL.problem;
  if (props.arrange?.activeId === node.id) return MODEL.accent;
  if (props.focus?.has(node.id)) return props.focusColor;
  return null;
}

function LockMark({ node }: { node: SceneNode }) {
  const top = new Vector3(node.transform.m[3], node.transform.m[11] + node.dimensions.z / 2 + 0.15, -node.transform.m[7]);
  return (
    <Html position={top} center style={{ pointerEvents: "none" }}>
      <span className="grid size-7 place-items-center rounded-full bg-ink text-paper shadow-md">
        <Lock size={14} weight="bold" aria-label="Fixed in place" />
      </span>
    </Html>
  );
}

function nodeState(node: SceneNode, props: Omit<ModelProps, "shown">) {
  return {
    faded: props.focus !== null && !props.focus.has(node.id),
    outline: edgeColor(node, props),
    lockable: props.arrange !== null && node.kind === "object" && !node.movable,
    selectable: props.focus === null || props.focus.has(node.id) ? props.arrange === null : false,
  };
}

function styledMaterial(source: Material | Material[], faded: boolean, clippingPlanes: Plane[] | null, stripPhotoMap: boolean): Material | Material[] {
  // eslint-disable-next-line complexity
  const style = (material: Material) => {
    const copy = material.clone();
    if (stripPhotoMap && copy instanceof MeshStandardMaterial) copy.map = null;
    copy.transparent = faded || material.transparent;
    copy.opacity = faded ? material.opacity * 0.15 : material.opacity;
    copy.depthWrite = faded ? false : material.depthWrite;
    copy.clippingPlanes = clippingPlanes?.map((plane) => plane.clone()) ?? material.clippingPlanes?.map((plane) => plane.clone()) ?? null;
    return copy;
  };
  return Array.isArray(source) ? source.map(style) : style(source);
}

function useSourceMaterial(source: Material | Material[] | null, faded: boolean, clipWall: boolean, stripPhotoMap: boolean) {
  const material = useMemo(
    () => source ? styledMaterial(source, faded, clipWall ? [WALL_CLIP_PLANE] : null, stripPhotoMap) : null,
    [source, faded, clipWall, stripPhotoMap],
  );
  useEffect(() => () => {
    if (Array.isArray(material)) material.forEach((item) => item.dispose());
    else material?.dispose();
  }, [material]);
  return material;
}

function coverageColor(fraction: number): string {
  if (fraction >= 0.8) return "#2f8f5b";
  if (fraction >= 0.4) return "#c99a32";
  return "#bd5252";
}

// eslint-disable-next-line complexity
function DisplayMaterial({ source, node, faded, clipWall, mode = "plain", stale = false, coverage }: { source: Material | Material[] | null; node: SceneNode; faded: boolean; clipWall: boolean; mode?: ModelProps["materialMode"]; stale?: boolean; coverage?: number }) {
  const canUseSource = mode !== "coverage" && !stale;
  const material = useSourceMaterial(canUseSource ? source : null, faded, clipWall, mode === "plain");
  if (material) return <primitive attach="material" object={material} />;
  return <meshStandardMaterial
    color={mode === "coverage" ? coverageColor(coverage ?? 0) : nodeColor(node)}
    roughness={0.92}
    transparent={faded}
    opacity={faded ? 0.15 : 1}
    depthWrite={!faded}
    clippingPlanes={clipWall ? [WALL_CLIP_PLANE] : null}
  />;
}

/** The renderer clips pixels, but Three's default raycast still sees them. */
function clippedWallRaycast(this: Mesh, raycaster: Raycaster, intersections: Intersection[]) {
  const start = intersections.length;
  Mesh.prototype.raycast.call(this, raycaster, intersections);
  for (let index = intersections.length - 1; index >= start; index -= 1) {
    if (intersections[index].point.y > WALL_CUT_HEIGHT) intersections.splice(index, 1);
  }
}

function clipsWall(node: SceneNode, cutWalls: boolean | undefined): boolean {
  return node.kind === "wall" && (cutWalls ?? true);
}

function meshRaycast(faded: boolean, clipWall: boolean) {
  if (faded) return () => null;
  return clipWall ? clippedWallRaycast : undefined;
}

// eslint-disable-next-line complexity
function ModelNode({ placed, ...props }: { placed: Placed } & Omit<ModelProps, "shown">) {
  const { node, geometry, matrix } = placed;
  const [hovered, setHovered] = useState(false);
  const { faded, outline, lockable, selectable } = nodeState(node, props);
  const drag = useDrag(node, props.arrange);
  const draggable = "onPointerDown" in drag;
  const clipWall = clipsWall(node, props.cutWalls);

  function select(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation();
    props.onSelectNode(node.id);
  }

  function hover(on: boolean) {
    setHovered(on);
    if (draggable) setCursor(on ? "grab" : "auto");
  }

  return (
    <mesh
      geometry={geometry}
      matrix={matrix}
      matrixAutoUpdate={false}
      castShadow={!faded && node.kind !== "floor"}
      receiveShadow
      onClick={selectable ? select : undefined}
      onPointerOver={() => hover(true)}
      onPointerOut={() => hover(false)}
      raycast={meshRaycast(faded, clipWall)}
      name={node.id}
      {...drag}
    >
      <DisplayMaterial source={placed.sourceMaterial} node={node} faded={faded} clipWall={clipWall} mode={props.materialMode} stale={props.staleNodeIds?.has(node.id)} coverage={props.coverage?.get(node.id)} />
      {outline && <Edges threshold={20} lineWidth={3} color={outline} renderOrder={5} clippingPlanes={clipWall ? [WALL_CLIP_PLANE] : null} />}
      {lockable && hovered && <LockMark node={node} />}
    </mesh>
  );
}

function ModelNodes({ placements, ...props }: { placements: Placed[] } & Omit<ModelProps, "shown">) {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => invalidate(), [placements, props.focus, props.arrange, invalidate]);
  return (
    <group>
      {placements.map((placed) => (
        <ModelNode key={placed.node.id} placed={placed} {...props} />
      ))}
    </group>
  );
}

function visibleNodes(scene: SceneGraph, includeFloors = false): SceneNode[] {
  return scene.nodes.filter((node) => !HIDDEN_KINDS.has(node.kind) && (includeFloors || node.kind !== "floor"));
}

export function GlbShopModel({ url, exported, ...props }: ModelProps & { url: string; exported: SceneGraph }) {
  const meshes = useGlbMeshes(url);
  const placements = useMemo(() => {
    const exportedById = new Map(exported.nodes.map((node) => [node.id, node]));
    return visibleNodes(props.shown, true).map((node) => placeFromGlb(meshes, node, exportedById.get(node.id), props.staleNodeIds?.has(node.id) ?? false)).filter((placed): placed is Placed => placed !== null);
  }, [meshes, exported, props.shown, props.staleNodeIds]);
  return <ModelNodes placements={placements} {...props} />;
}

export function BoxShopModel(props: ModelProps) {
  const placements = useMemo(
    () => visibleNodes(props.shown).map((node) => ({ node, geometry: UNIT_BOX, matrix: boxMatrix(node), sourceMaterial: null })),
    [props.shown],
  );
  return <ModelNodes placements={placements} {...props} />;
}
