import { Box3, Matrix4, PerspectiveCamera, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { capturedMeshUrl, lidarGeometry, lidarMatrix, objectAtPoint, validateLidarMesh } from "./lidar-mesh";
import type { LidarMesh, SceneGraph } from "@/types/contracts";
import { fitPoseToBounds } from "./camera";

function scannedTriangle(): LidarMesh {
  return { floorY: -1.5, peopleFilteringEnabled: true, parts: [{
    id: "87f80820-9062-4ac9-9c55-65cbe768cd45",
    transform: new Matrix4().makeTranslation(2, -1.5, 3).toArray(),
    vertices: [0, 0, 0, 0.2, 0, 0, 0, 0.3, 0], triangles: [0, 1, 2],
  }] };
}

describe("measured LiDAR surfaces", () => {
  it("shows captured evidence only when requested for the original room", () => {
    expect(capturedMeshUrl("/scan/mesh", 0, true)).toBe("/scan/mesh");
    expect(capturedMeshUrl("/scan/mesh", 0, false)).toBeNull();
    expect(capturedMeshUrl("/scan/mesh", 1, true)).toBeNull();
    expect(capturedMeshUrl(null, 0, true)).toBeNull();
  });
  it("frames all measured corners even in a narrow phone viewport", () => {
    const bounds = new Box3(new Vector3(-4, 0, -3), new Vector3(4, 3, 3));
    const pose = fitPoseToBounds({ position: [4, 5, 6], target: [0, 0, 0], fov: 50 }, bounds, 0.5);
    const camera = new PerspectiveCamera(pose.fov, 0.5, 0.05, 200);
    camera.position.fromArray(pose.position);
    camera.lookAt(new Vector3(...pose.target));
    camera.updateMatrixWorld();
    for (const x of [-4, 4]) for (const y of [0, 3]) for (const z of [-3, 3]) {
      const projected = new Vector3(x, y, z).project(camera);
      expect(Math.abs(projected.x)).toBeLessThan(1);
      expect(Math.abs(projected.y)).toBeLessThan(1);
    }
  });
  it("preserves the actual triangle and aligns the same floor as scene ingest", () => {
    const mesh = validateLidarMesh(scannedTriangle());
    const part = mesh.parts[0];
    const geometry = lidarGeometry(part);
    expect(Array.from(geometry.index!.array)).toEqual([0, 1, 2]);
    expect(geometry.getAttribute("position").count).toBe(3);
    expect(new Vector3(0, 0, 0).applyMatrix4(lidarMatrix(part, mesh.floorY!)).toArray()).toEqual([2, 0, 3]);
    expect(new Vector3(0.2, 0, 0).applyMatrix4(lidarMatrix(part, mesh.floorY!)).toArray()).toEqual([2.2, 0, 3]);
    geometry.dispose();
  });

  it("rejects broken geometry instead of rendering a replacement box", () => {
    const mesh = scannedTriangle();
    mesh.parts[0].triangles[2] = 99;
    expect(() => validateLidarMesh(mesh)).toThrow("indices");
    expect(() => validateLidarMesh({ ...scannedTriangle(), floorY: null })).toThrow("alignment");
  });

  it("matches a real surface point to one object, leaving ambiguous geometry unlabelled", () => {
    const scene: SceneGraph = { scan_id: "scan", revision: 0, base_hash: null, nodes: [{
      id: "table", kind: "object", label: "Table", dimensions: { x: 2, y: 0.5, z: 1 },
      transform: { m: [1, 0, 0, 2, 0, 1, 0, 0, 0, 0, 1, 0.5, 0, 0, 0, 1] },
      raw_category: "table", quality: "measured", movable: true, labeled_by: "roomplan", parent_id: null,
    }] };
    expect(objectAtPoint(scene, new Vector3(2, 0.9, 0))?.label).toBe("Table");
    expect(objectAtPoint(scene, new Vector3(2, 0.9, 1))).toBeNull();
    expect(objectAtPoint({ ...scene, nodes: [...scene.nodes, ...scene.nodes] }, new Vector3(2, 0.9, 0))).toBeNull();
  });
});
