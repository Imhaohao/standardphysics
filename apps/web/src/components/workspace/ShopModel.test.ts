import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { DataTexture, Mesh, MeshStandardMaterial } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { describe, expect, it } from "vitest";
import { withoutBareMetal } from "./ShopModel";

const SAMPLE_SHOP_GLB = fileURLToPath(new URL("../../../../../packages/fixtures/standardphysics_fixtures/data/shop_lawsuit.glb", import.meta.url));

/** The first material the sample shop's model arrives with, through the same loader the viewer uses. */
async function sampleShopMaterial(): Promise<MeshStandardMaterial> {
  const bytes = readFileSync(SAMPLE_SHOP_GLB);
  const gltf = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "");
  let material: MeshStandardMaterial | null = null;
  gltf.scene.traverse((object) => {
    if (!material && object instanceof Mesh) material = object.material as MeshStandardMaterial;
  });
  if (!material) throw new Error("the sample shop's model has no meshes");
  return material;
}

describe("drawing a model's own materials", () => {
  it("draws the bare metal the sample shop's material-less model arrives in as a plain surface", async () => {
    const material = (await sampleShopMaterial()).clone();
    expect(material.metalness).toBe(1);
    withoutBareMetal(material);
    expect(material.metalness).toBe(0);
  });

  it("keeps a finish the export chose as metal", () => {
    const metal = new MeshStandardMaterial({ metalness: 0.8, roughness: 0.28 });
    withoutBareMetal(metal);
    expect(metal.metalness).toBe(0.8);
  });

  it("keeps full metal that carries its own metalness map", () => {
    const mapped = new MeshStandardMaterial({ metalness: 1, metalnessMap: new DataTexture() });
    withoutBareMetal(mapped);
    expect(mapped.metalness).toBe(1);
  });
});
