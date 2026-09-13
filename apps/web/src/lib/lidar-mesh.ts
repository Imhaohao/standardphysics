import { BufferGeometry, Float32BufferAttribute, Matrix4, Vector3 } from "three";
import type { LidarMesh, LidarMeshPart, SceneGraph, SceneNode } from "@/types/contracts";
import { toViewerMatrix } from "./scene-matrix";

/** Raw triangles stay as an underlay on the original room. Furniture is the object graph. */
export function capturedMeshUrl(url: string | null, revision: number, layoutPreview: boolean): string | null {
  return revision === 0 && !layoutPreview ? url : null;
}

/** Raw ARKit and the viewer both use Y-up. Only the ingest floor shift applies. */
export function lidarMatrix(part: LidarMeshPart, floorY: number): Matrix4 {
  return new Matrix4().makeTranslation(0, -floorY, 0).multiply(new Matrix4().fromArray(part.transform));
}

export function lidarGeometry(part: LidarMeshPart): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(part.vertices, 3));
  geometry.setIndex(part.triangles);
  geometry.computeVertexNormals();
  return geometry;
}

export function validateLidarMesh(value: unknown): LidarMesh {
  const mesh = value as LidarMesh;
  validateMeshHeader(mesh);
  let vertices = 0;
  let triangles = 0;
  for (const part of mesh.parts) {
    validatePart(part);
    vertices += part.vertices.length / 3;
    triangles += part.triangles.length / 3;
  }
  if (vertices > 2_000_000 || triangles > 4_000_000) throw new Error("Scan surfaces exceed the viewer limit");
  return mesh;
}

function validateMeshHeader(mesh: LidarMesh) {
  if (!mesh || !Array.isArray(mesh.parts) || !mesh.parts.length || mesh.parts.length > 4096) throw new Error("Invalid scan surfaces");
  if (!Number.isFinite(mesh.floorY)) throw new Error("Scan surfaces need floor alignment");
}

function validateTransform(part: LidarMeshPart) {
  if (!part || !Array.isArray(part.transform) || part.transform.length !== 16 || !part.transform.every(Number.isFinite)) throw new Error("Invalid scan transform");
}

function validatePart(part: LidarMeshPart) {
  validateTransform(part);
  if (!isTriples(part.vertices) || !part.vertices.every(Number.isFinite)) throw new Error("Invalid scan vertices");
  if (!isTriples(part.triangles)) throw new Error("Invalid scan faces");
  const count = part.vertices.length / 3;
  if (!part.triangles.every((index) => Number.isInteger(index) && index >= 0 && index < count)) throw new Error("Invalid scan indices");
}

function isTriples(values: unknown): values is number[] {
  return Array.isArray(values) && values.length > 0 && values.length % 3 === 0;
}

/** Matching annotates measured geometry; it never manufactures a box in its place. */
export function objectAtPoint(scene: SceneGraph, point: Vector3): SceneNode | null {
  const matches = scene.nodes.filter((node) => {
    if (node.kind !== "object") return false;
    const local = point.clone().applyMatrix4(toViewerMatrix(node.transform).invert());
    return Math.abs(local.x) <= node.dimensions.x / 2 + 0.03
      && Math.abs(local.y) <= node.dimensions.z / 2 + 0.03
      && Math.abs(local.z) <= node.dimensions.y / 2 + 0.03;
  });
  return matches.length === 1 ? matches[0] : null;
}
