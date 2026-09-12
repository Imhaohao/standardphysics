import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Box3, Mesh, Vector3, type Object3D } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { describe, expect, it } from "vitest";
import type { SceneGraph } from "@/types/contracts";
import { toViewerMatrix } from "./scene-matrix";

const FIXTURES = join(__dirname, "../../../../packages/fixtures/standardphysics_fixtures/data");
const graph = JSON.parse(readFileSync(join(FIXTURES, "shop.scene_graph.json"), "utf8")) as SceneGraph;

async function loadShop(): Promise<Object3D> {
  const bytes = readFileSync(join(FIXTURES, "shop.glb"));
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const gltf = await new GLTFLoader().parseAsync(buffer, "");
  gltf.scene.updateMatrixWorld(true);
  return gltf.scene;
}

function meshesByName(root: Object3D): Map<string, Mesh> {
  const found = new Map<string, Mesh>();
  root.traverse((object) => {
    if (object instanceof Mesh) found.set(object.name, object);
  });
  return found;
}

describe("the committed shop.glb", () => {
  it("names a mesh after every SceneGraph node, exactly", async () => {
    const names = [...meshesByName(await loadShop()).keys()].sort();
    expect(names).toEqual(graph.nodes.map((node) => node.id).sort());
  });

  it("puts every mesh where the SceneGraph says the node is", async () => {
    const meshes = meshesByName(await loadShop());
    for (const node of graph.nodes) {
      const box = new Box3().setFromObject(meshes.get(node.id)!);
      const expected = new Vector3().setFromMatrixPosition(toViewerMatrix(node.transform));
      const size = box.getSize(new Vector3());
      expect(box.getCenter(new Vector3()).distanceTo(expected)).toBeLessThan(0.001);
      expect([size.x, size.y, size.z].map((v) => +v.toFixed(3))).toEqual(
        [node.dimensions.x, node.dimensions.z, node.dimensions.y].map((v) => +v.toFixed(3)),
      );
    }
  });
});
