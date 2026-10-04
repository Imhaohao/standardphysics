"use client";

import { useGLTF } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { BackSide, BufferGeometry, DoubleSide, Group, LinearFilter, Matrix4, Mesh, MeshBasicMaterial, Plane, Vector3, type Color, type Material, type Object3D, type Texture } from "three";
import { carveGeometry, carveRegion, type CarveRegion } from "@/lib/carve-scan";
import { movedFromScan, shadowCasters } from "@/lib/scan-shadows";
import { toViewerMatrix } from "@/lib/scene-matrix";
import { MoveMarks } from "./MoveMarks";
import { catchShadowsOn, shadowCatcherMaterial } from "./shadowCatcher";
import type { SceneGraph, SceneNode } from "@/types/contracts";

/** The colour of a surface seen from the side the phone never stood on. */
const UNMEASURED = "#8d8880";

type PhotographSourceMaterial = Material & {
  alphaMap?: Texture | null;
  color?: Color;
  emissiveMap?: Texture | null;
  map?: Texture | null;
};

/**
 * The photograph with no smaller copies of itself to fall back on.
 *
 * The scan's atlas packs every face as its own small island, so the half- and
 * quarter-size copies a GPU samples from a distance blend each island into its
 * neighbours, and a floor seen from across the room was crossed with light
 * lines. Sampling the full-size photograph keeps each face's own pixels. The
 * copy shares the image, so the GLTF's texture is left as it was.
 */
export function withoutMipmaps(texture: Texture | null): Texture | null {
  if (!texture) return null;
  const copy = texture.clone();
  copy.minFilter = LinearFilter;
  copy.generateMipmaps = false;
  copy.needsUpdate = true;
  copy.userData = { ...copy.userData, ownedByPaintedScan: true };
  return copy;
}

/**
 * Creates an unlit display material without changing the GLTF-owned source material or textures.
 *
 * Both faces go into a shadow map. The scan is an open surface, one triangle
 * thick, and a shadow pass draws only the faces turned away from the light, so
 * a moved table's top, which faces the light, threw no shadow at all.
 */
export function paintedMaterial(source: Material, vertexColors: boolean): MeshBasicMaterial {
  const photographic = source as PhotographSourceMaterial;
  const usesEmissiveMap = !photographic.map && Boolean(photographic.emissiveMap);
  return new MeshBasicMaterial({
    alphaMap: photographic.alphaMap ?? null,
    alphaTest: source.alphaTest,
    blending: source.blending,
    color: usesEmissiveMap ? "#ffffff" : photographic.color?.clone() ?? "#ffffff",
    depthTest: source.depthTest,
    depthWrite: source.depthWrite,
    map: withoutMipmaps(photographic.map ?? photographic.emissiveMap ?? null),
    opacity: source.opacity,
    side: source.side,
    shadowSide: DoubleSide,
    transparent: source.transparent,
    vertexColors,
  });
}

export function paintedMaterials(source: Material | Material[], vertexColors: boolean): Material | Material[] {
  return Array.isArray(source) ? source.map((material) => paintedMaterial(material, vertexColors)) : paintedMaterial(source, vertexColors);
}

export function hasVertexColors(mesh: Mesh): boolean {
  const color = mesh.geometry.getAttribute("color");
  return color !== undefined && color.itemSize >= 3;
}

function disposePaintedMaterial(material: Material) {
  const map = (material as MeshBasicMaterial).map;
  if (map?.userData.ownedByPaintedScan) map.dispose();
  material.dispose();
}

function disposePaintedMaterials(material: Material | Material[]) {
  if (Array.isArray(material)) material.forEach(disposePaintedMaterial);
  else disposePaintedMaterial(material);
}

/**
 * A second pass that closes the scan from behind.
 *
 * A phone walked past a desk measures its top and never the underside, so the
 * scan holds a real surface with nothing below it. Drawn from the front only,
 * that surface vanishes when the camera drops beneath it, and a room read as
 * scattered fragments hanging in the air: a table appeared to float because
 * its legs were not there to hold it up, and the top itself disappeared the
 * moment you looked up at it.
 *
 * Backfaces are drawn in one flat unlit colour instead. The scan then reads as
 * a shell with holes in it, and every hole is the shape of somewhere the phone
 * was never pointed. Nothing is filled in and no surface is moved; the blank
 * grey is the absence of a measurement, which is what it looks like.
 */
function unmeasuredSide(source: Material): MeshBasicMaterial {
  return new MeshBasicMaterial({
    color: UNMEASURED,
    depthTest: source.depthTest,
    depthWrite: true,
    side: BackSide,
  });
}

function backfaceShell(mesh: Mesh): Mesh {
  const shell = new Mesh(mesh.geometry, unmeasuredSide(asOne(mesh.material)));
  shell.raycast = () => null;
  shell.renderOrder = -1;
  return shell;
}

function asOne(material: Material | Material[]): Material {
  return Array.isArray(material) ? material[0] : material;
}

const NOT_PICKABLE = () => null;
const NO_CASTERS = new Set<string>();

/** The pieces the owner may move, cut out of the scan so each one can follow its own box; null leaves the scan whole. */
export type ScanPieces = { carve: SceneNode[]; placed: SceneGraph };

/**
 * One piece cut out of the scan: the group its triangles hang on, the parts
 * that cast once it has moved, and the catchers that shade it while it stays.
 */
export type ScanPiece = { group: Group; parts: Mesh[]; catchers: Mesh[] };

/**
 * The painted room and its cut-out pieces, the room's own shadow catchers,
 * and what painting made so it can be released with them.
 */
export type Painted = {
  room: Object3D;
  surfaces: Mesh[];
  catchers: Mesh[];
  pieces: Map<string, ScanPiece>;
  made: { geometries: BufferGeometry[]; materials: Material[] };
};

/**
 * The captured surface with the colour the photos gave it.
 *
 * Colour rides on the vertices, already the brightness the room was, so the
 * material is unlit: lighting it a second time would double the shadows that
 * are in the photographs. The scan is one piece of geometry and the graph is
 * what owns objects, so nothing here can be picked or dragged. While a layout
 * is being planned, each movable piece's triangles are cut out and drawn where
 * its box now stands, so moving the counter moves the scanned counter.
 *
 * With `shadows`, a moved piece also throws a shadow onto the room around it.
 * Only a moved piece casts: everything still where it was scanned already has
 * its real shadow in the photographs.
 */
export function PaintedScan({ url, cutAbove = null, pieces = null, shadows = false }: { url: string; cutAbove?: number | null; pieces?: ScanPieces | null; shadows?: boolean }) {
  const { scene } = useGLTF(url);
  const { carve, catching } = carving(pieces, shadows);
  const painted = useMemo(() => paintScan(scene, carve, { catching, cutAbove }), [scene, carve, catching, cutAbove]);
  useEffect(() => () => disposePainted(painted), [painted]);
  useShadowRoles(painted, catching ? pieces : null);
  return (
    <>
      <primitive object={painted.room} />
      {pieces && <MovedPieces painted={painted} pieces={pieces} shadows={catching} />}
    </>
  );
}

/** What to cut out of the scan, and whether what is cut out throws shadows once it moves. */
function carving(pieces: ScanPieces | null, shadows: boolean) {
  const carve = pieces?.carve ?? null;
  return { carve, catching: shadows && carve !== null };
}

/** Every piece cut out of the scan, hung where its box now stands. */
function MovedPieces({ painted, pieces, shadows }: { painted: Painted; pieces: ScanPieces; shadows: boolean }) {
  return pieces.carve.map((node) => {
    const piece = painted.pieces.get(node.id);
    const now = pieces.placed.nodes.find((candidate) => candidate.id === node.id) ?? node;
    return piece ? <MovedPiece key={node.id} group={piece.group} from={node} to={now} shadows={shadows} /> : null;
  });
}

/**
 * The scan painted, cut into its pieces when `carve` names them, laid with
 * shadow catchers when `catching`, and cut off above `cutAbove`.
 */
export function paintScan(scene: Object3D, carve: SceneNode[] | null, { catching, cutAbove }: { catching: boolean; cutAbove: number | null }): Painted {
  const painted = paint(scene, carve);
  if (catching) layCatchers(painted);
  cutAt(painted, cutAbove);
  return painted;
}

function paint(scene: Object3D, carve: SceneNode[] | null): Painted {
  const room = scene.clone(true);
  room.updateMatrixWorld(true);
  const regions = carve?.map(carveRegion) ?? [];
  const painted: Painted = { room, surfaces: [], catchers: [], pieces: new Map(), made: { geometries: [], materials: [] } };
  room.traverse((object) => { if (object instanceof Mesh) painted.surfaces.push(object); });
  for (const mesh of painted.surfaces) {
    mesh.material = paintedMaterials(mesh.material, hasVertexColors(mesh));
    mesh.raycast = NOT_PICKABLE;
    if (regions.length > 0) carveInto(mesh, regions, painted);
    mesh.add(backfaceShell(mesh));
  }
  return painted;
}

/** Takes each piece's triangles out of the mesh and hangs them, still where they were scanned, on that piece's group. */
function carveInto(mesh: Mesh, regions: CarveRegion[], { pieces, made }: Painted) {
  const carved = carveGeometry(mesh.geometry, mesh.matrixWorld, regions);
  mesh.geometry = carved.room ?? new BufferGeometry();
  made.geometries.push(mesh.geometry);
  for (const [id, geometry] of carved.pieces) {
    const part = new Mesh(geometry, mesh.material);
    part.matrixAutoUpdate = false;
    part.matrix.copy(mesh.matrixWorld);
    part.raycast = NOT_PICKABLE;
    const shell = backfaceShell(part);
    part.add(shell);
    const piece = scanPiece(pieces, id);
    piece.group.add(part);
    piece.parts.push(part);
    made.geometries.push(geometry);
    made.materials.push(shell.material as Material);
  }
}

function scanPiece(pieces: Map<string, ScanPiece>, id: string): ScanPiece {
  const existing = pieces.get(id);
  if (existing) return existing;
  const piece: ScanPiece = { group: new Group(), parts: [], catchers: [] };
  pieces.set(id, piece);
  return piece;
}

/** One shadow catcher over every painted surface, the room's and each piece's, all sharing one material. */
function layCatchers(painted: Painted) {
  const material = shadowCatcherMaterial();
  painted.made.materials.push(material);
  painted.catchers = painted.surfaces.map((surface) => catchShadowsOn(surface, material));
  for (const piece of painted.pieces.values()) piece.catchers = piece.parts.map((part) => catchShadowsOn(part, material));
}

/**
 * Who casts and who catches. A moved piece casts and catches nothing, since
 * shading itself would darken a photograph that already shows how it is lit.
 * The room and every piece still in place catch, but only while something
 * casts: a catcher is a second pass over its whole surface.
 */
export function showShadows({ catchers, pieces }: Painted, casters: Set<string>) {
  const casting = [...pieces.keys()].some((id) => casters.has(id));
  for (const catcher of catchers) catcher.visible = casting;
  for (const [id, piece] of pieces) {
    const moved = casters.has(id);
    for (const part of piece.parts) part.castShadow = moved;
    for (const catcher of piece.catchers) catcher.visible = casting && !moved;
  }
}

/** Keeps who casts and who catches in step with the layout, and draws a frame whenever that changes. */
function useShadowRoles(painted: Painted, pieces: ScanPieces | null) {
  const invalidate = useThree((state) => state.invalidate);
  const casters = useMemo(() => (pieces ? shadowCasters(pieces.carve, pieces.placed) : NO_CASTERS), [pieces]);
  useLayoutEffect(() => {
    showShadows(painted, casters);
    invalidate();
  }, [painted, casters, invalidate]);
}

/** The rigid move from where a piece was scanned to where its box stands now. */
function moveBetween(from: SceneNode, to: SceneNode): Matrix4 {
  return toViewerMatrix(to.transform).multiply(toViewerMatrix(from.transform).invert());
}

/**
 * A scanned piece drawn where its box now stands, with marks on the floor for
 * where it was, where it went and how it got there.
 */
function MovedPiece({ group, from, to, shadows }: { group: Group; from: SceneNode; to: SceneNode; shadows: boolean }) {
  const invalidate = useThree((state) => state.invalidate);
  const mover = useRef<Group>(null);
  useLayoutEffect(() => {
    if (!mover.current) return;
    mover.current.matrix.copy(moveBetween(from, to));
    mover.current.matrixWorldNeedsUpdate = true;
    invalidate();
  }, [from, to, invalidate]);
  return (
    <>
      <group ref={mover} matrixAutoUpdate={false}><primitive object={group} /></group>
      {movedFromScan(from, to) && <MoveMarks from={from} to={to} shadows={shadows} />}
    </>
  );
}

function disposePainted({ room, made }: Painted) {
  room.traverse((object) => {
    if (object instanceof Mesh) disposePaintedMaterials(object.material);
  });
  made.geometries.forEach((geometry) => geometry.dispose());
  made.materials.forEach((material) => material.dispose());
}

/**
 * Everything above `height` left out, so a view from above looks into the
 * rooms rather than onto a ceiling. The cut-out pieces are cut too, their
 * grey backs and their shadow catchers along with their photographs.
 */
function cutAt({ room, pieces }: Painted, height: number | null) {
  const planes = height === null ? null : [new Plane(new Vector3(0, -1, 0), height)];
  const clip = (object: Object3D) => {
    if (!(object instanceof Mesh)) return;
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) material.clippingPlanes = planes;
  };
  room.traverse(clip);
  for (const piece of pieces.values()) piece.group.traverse(clip);
}
