import { BackSide, BufferAttribute, BufferGeometry, DataTexture, DoubleSide, Group, LinearFilter, LinearMipmapLinearFilter, Mesh, MeshBasicMaterial, MeshStandardMaterial, RGBAFormat, ShadowMaterial, UnsignedByteType, type Material, type Object3D } from "three";
import { describe, expect, it } from "vitest";
import type { Mat4, SceneNode } from "@/types/contracts";
import { hasVertexColors, paintedMaterial, paintedMaterials, paintScan, showShadows, type Painted } from "./PaintedScan";

function texture() {
  return new DataTexture(new Uint8Array([255, 255, 255, 255]), 1, 1, RGBAFormat, UnsignedByteType);
}

describe("painted scan materials", () => {
  it("keeps the UV photograph and vertex colors without mutating the GLTF material", () => {
    const map = texture();
    const alphaMap = texture();
    const source = new MeshStandardMaterial({ map, alphaMap, opacity: 0.6, transparent: true, side: BackSide });

    const painted = paintedMaterial(source, true);

    expect(painted).toBeInstanceOf(MeshBasicMaterial);
    expect(painted.map?.image).toBe(map.image);
    expect(painted.alphaMap).toBe(alphaMap);
    expect(painted.vertexColors).toBe(true);
    expect(painted.opacity).toBe(0.6);
    expect(painted.transparent).toBe(true);
    expect(painted.side).toBe(BackSide);
    expect(source.map).toBe(map);
    expect(source.alphaMap).toBe(alphaMap);
    expect(source.vertexColors).toBe(false);
  });

  it("uses an emissive photograph when it is the unlit source and preserves material groups", () => {
    const emissiveMap = texture();
    const source = new MeshStandardMaterial({ emissiveMap });
    const group = paintedMaterials([source, new MeshBasicMaterial({ vertexColors: true })], false);

    expect(Array.isArray(group)).toBe(true);
    if (!Array.isArray(group)) throw new Error("expected material group");
    expect(group).toHaveLength(2);
    expect((group[0] as MeshBasicMaterial).map?.image).toBe(emissiveMap.image);
    expect((group[0] as MeshBasicMaterial).color.getHex()).toBe(0xffffff);
    expect(source.emissiveMap).toBe(emissiveMap);
  });

  it("does not enable vertex colors for a UV-only photogrammetry primitive", () => {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(new Float32Array([0, 0, 0]), 3));
    geometry.setAttribute("uv", new BufferAttribute(new Float32Array([0, 0]), 2));
    const mesh = new Mesh(geometry, new MeshStandardMaterial({ emissiveMap: texture() }));

    expect(hasVertexColors(mesh)).toBe(false);
    const painted = paintedMaterial(mesh.material, hasVertexColors(mesh));
    expect(painted.vertexColors).toBe(false);
    expect(painted.map?.image).toBe(mesh.material.emissiveMap?.image);
  });

  it("samples the full-size photograph, since faces packed one by one bleed into each other when shrunk", () => {
    const map = texture();
    map.minFilter = LinearMipmapLinearFilter;
    map.generateMipmaps = true;
    const painted = paintedMaterial(new MeshStandardMaterial({ map }), false);

    expect(painted.map?.minFilter).toBe(LinearFilter);
    expect(painted.map?.generateMipmaps).toBe(false);
    expect(map.minFilter).toBe(LinearMipmapLinearFilter);
    expect(map.generateMipmaps).toBe(true);
  });

  it("puts both faces of the one-triangle-thick scan into a shadow map, so a table's top shades the floor", () => {
    expect(paintedMaterial(new MeshStandardMaterial(), false).shadowSide).toBe(DoubleSide);
  });
});

/** A piece standing on the floor at scene (x, y), as the graph measures it. */
function piece(id: string, x: number, y: number, size: { x: number; y: number; z: number }): SceneNode {
  return {
    id, kind: "object", label: id, raw_category: "table", quality: "measured", movable: true, dimensions: size,
    transform: { m: [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, size.z / 2, 0, 0, 0, 1] } as Mat4,
  } as SceneNode;
}

const counter = piece("counter", 3, 4, { x: 2, y: 0.6, z: 1 });
const chair = piece("chair", 0, 0, { x: 0.45, y: 0.45, z: 0.9 });

/** A small triangle centred on a viewer-space point (y up, scene y becomes -z). */
function triangleAt(x: number, y: number, z: number): number[] {
  return [x - 0.01, y, z, x + 0.01, y, z, x, y + 0.01, z];
}

/** One scanned mesh holding the counter's top, the chair's seat, open floor and a wall. */
function scannedRoom(): Group {
  const geometry = new BufferGeometry();
  const triangles = [triangleAt(3, 0.99, -4), triangleAt(0, 0.45, 0), triangleAt(1.5, 0, -2), triangleAt(-3, 1, 0)];
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(triangles.flat()), 3));
  const room = new Group();
  room.add(new Mesh(geometry, new MeshStandardMaterial()));
  return room;
}

function catchersIn(root: Object3D): Mesh[] {
  const found: Mesh[] = [];
  root.traverse((object) => { if (object instanceof Mesh && object.material instanceof ShadowMaterial) found.push(object); });
  return found;
}

function materialsIn(painted: Painted): Material[] {
  const found: Material[] = [];
  const collect = (object: Object3D) => { if (object instanceof Mesh) found.push(...[object.material].flat()); };
  painted.room.traverse(collect);
  for (const cutOut of painted.pieces.values()) cutOut.group.traverse(collect);
  return found;
}

describe("shadows on the painted scan", () => {
  const paintedWithCatchers = () => paintScan(scannedRoom(), [counter, chair], { catching: true, cutAbove: null });

  it("lays a hidden catcher over the room and over every cut-out piece, each on that surface's own triangles", () => {
    const painted = paintedWithCatchers();
    expect(painted.catchers).toHaveLength(1);
    expect(painted.catchers[0].geometry).toBe(painted.surfaces[0].geometry);
    for (const cutOut of painted.pieces.values()) {
      expect(cutOut.catchers.map((catcher) => catcher.geometry)).toEqual(cutOut.parts.map((part) => part.geometry));
    }
    expect(catchersIn(painted.room).every((catcher) => !catcher.visible)).toBe(true);
  });

  it("casts from the moved piece alone and lets the room and the pieces still in place catch it", () => {
    const painted = paintedWithCatchers();
    showShadows(painted, new Set(["chair"]));
    const [moved, stayed] = [painted.pieces.get("chair")!, painted.pieces.get("counter")!];

    expect(moved.parts.every((part) => part.castShadow)).toBe(true);
    expect(moved.catchers.every((catcher) => !catcher.visible)).toBe(true);
    expect(stayed.parts.some((part) => part.castShadow)).toBe(false);
    expect(stayed.catchers.every((catcher) => catcher.visible)).toBe(true);
    expect(painted.catchers.every((catcher) => catcher.visible)).toBe(true);
    expect(painted.surfaces[0].castShadow).toBe(false);
  });

  it("puts everything back when the piece returns to its scanned spot", () => {
    const painted = paintedWithCatchers();
    showShadows(painted, new Set(["chair"]));
    showShadows(painted, new Set());

    const everyPart = [...painted.pieces.values()].flatMap((cutOut) => cutOut.parts);
    expect(everyPart.some((part) => part.castShadow)).toBe(false);
    expect([...painted.catchers, ...[...painted.pieces.values()].flatMap((cutOut) => cutOut.catchers)].some((catcher) => catcher.visible)).toBe(false);
  });

  it("leaves catchers out entirely when the device draws no shadows", () => {
    const painted = paintScan(scannedRoom(), [counter, chair], { catching: false, cutAbove: null });
    expect(painted.catchers).toHaveLength(0);
    expect([...painted.pieces.values()].every((cutOut) => cutOut.catchers.length === 0)).toBe(true);
  });

  it("cuts every surface off at the same height, the pieces' grey backs and the catchers included", () => {
    const painted = paintScan(scannedRoom(), [counter, chair], { catching: true, cutAbove: 2.2 });
    const materials = materialsIn(painted);
    expect(materials.some((material) => material instanceof ShadowMaterial)).toBe(true);
    expect(materials.every((material) => material.clippingPlanes?.[0]?.constant === 2.2)).toBe(true);
  });
});
