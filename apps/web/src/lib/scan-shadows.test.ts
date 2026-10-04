import { Box3, OrthographicCamera, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import sceneGraph from "@fixtures/shop.scene_graph.json";
import type { Mat4, SceneGraph, SceneNode } from "@/types/contracts";
import { applyMoves } from "./moves";
import { castsShadow, lightCasts, movedFromScan, roomBounds, shadowCasters, shadowRig, TOWARD_LIGHT } from "./scan-shadows";

const shop = sceneGraph as unknown as SceneGraph;
const byLabel = (label: string) => shop.nodes.find((node) => node.label === label)!;
const chair = byLabel("Chair");
const furniture = shop.nodes.filter((node) => node.kind === "object");

function moved(node: SceneNode, dx: number, dy: number, degrees = 0): SceneGraph {
  return applyMoves(shop, { [node.id]: { node_id: node.id, delta_translation: { x: dx, y: dy, z: 0 }, delta_rotation_z_degrees: degrees } });
}

function withTransform(node: SceneNode, change: (m: number[]) => void): SceneNode {
  const m = [...node.transform.m];
  change(m);
  return { ...node, transform: { m } as Mat4 };
}

describe("which pieces throw a shadow onto the photographed room", () => {
  it("leaves every piece still standing where it was scanned in the photograph's own shadow", () => {
    expect(shadowCasters(furniture, shop).size).toBe(0);
  });

  it("casts from a piece slid across the floor, and from nothing else", () => {
    expect([...shadowCasters(furniture, moved(chair, 0.4, -0.2))]).toEqual([chair.id]);
  });

  it("casts from a piece turned where it stands", () => {
    expect([...shadowCasters(furniture, moved(chair, 0, 0, 90))]).toEqual([chair.id]);
  });

  it("casts from a piece lifted onto something, though it never moved across the floor", () => {
    expect(movedFromScan(chair, withTransform(chair, (m) => { m[11] += 0.75; }))).toBe(true);
  });

  it("ignores the rounding a transform picks up on its way through the server", () => {
    expect(movedFromScan(chair, withTransform(chair, (m) => { m[3] += 1e-6; m[0] -= 1e-7; }))).toBe(false);
  });

  it("casts from a piece the scan never saw, which has no shadow in the photographs", () => {
    const added = { ...chair, id: "new-chair" };
    expect(castsShadow(undefined, added)).toBe(true);
    expect([...shadowCasters(furniture, { ...shop, nodes: [...shop.nodes, added] })]).toEqual(["new-chair"]);
  });

  it("never casts from the room itself, whatever happens to its walls", () => {
    const wall = shop.nodes.find((node) => node.kind === "wall")!;
    const shifted = { ...shop, nodes: shop.nodes.map((node) => (node.id === wall.id ? withTransform(node, (m) => { m[3] += 1; }) : node)) };
    expect(shadowCasters(furniture, shifted).size).toBe(0);
  });
});

describe("when the light casts at all", () => {
  it("lights the boxes like the model they are, every box casting", () => {
    expect(lightCasts("boxes", false)).toBe(true);
  });

  it("casts on the painted scan only while furniture can move across it", () => {
    expect(lightCasts("scan", true)).toBe(true);
    expect(lightCasts("scan", false)).toBe(false);
  });

  it("never casts on the splats or the combined walks, which have nothing cut out to move", () => {
    expect(lightCasts("splats", true)).toBe(false);
    expect(lightCasts("combined", true)).toBe(false);
  });
});

describe("the light over the room", () => {
  it("stands fifteen degrees off overhead, so a shadow lands about a quarter of a piece's height away", () => {
    const fromVertical = (Math.acos(TOWARD_LIGHT.y / TOWARD_LIGHT.length()) * 180) / Math.PI;
    expect(fromVertical).toBeCloseTo(15, 5);
    expect(-TOWARD_LIGHT.x / TOWARD_LIGHT.y).toBeCloseTo(0.268, 3);
  });

  it("measures the room from its walls, floor and furniture, in viewer space", () => {
    const bounds = roomBounds(shop);
    expect(bounds.min.toArray().map((value) => +value.toFixed(3))).toEqual([-3.05, -0.005, -4.05]);
    expect(bounds.max.toArray().map((value) => +value.toFixed(3))).toEqual([3.05, 3, 4.05]);
  });

  it("skips a node whose transform is not a number rather than losing the whole room", () => {
    const broken = withTransform(chair, (m) => { m[3] = Number.NaN; });
    expect(roomBounds({ ...shop, nodes: [...shop.nodes, broken] }).equals(roomBounds(shop))).toBe(true);
  });

  it("still stands a light over a room with nothing measured in it", () => {
    expect(roomBounds({ ...shop, nodes: [] }).isEmpty()).toBe(false);
  });
});

/** The rig's shadow camera, aimed the way three aims a DirectionalLight's. */
function shadowCamera(room: Box3) {
  const rig = shadowRig(room, 0.05);
  const camera = new OrthographicCamera(rig.left, rig.right, rig.top, rig.bottom, rig.near, rig.far);
  camera.position.copy(rig.position);
  camera.lookAt(rig.target);
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  return { rig, camera };
}

function corners(box: Box3): Vector3[] {
  return [box.min.x, box.max.x].flatMap((x) => [box.min.y, box.max.y].flatMap((y) => [box.min.z, box.max.z].map((z) => new Vector3(x, y, z))));
}

describe("framing the shadow camera on the room", () => {
  const room = roomBounds(shop);
  const { rig, camera } = shadowCamera(room);
  const projected = corners(room.clone().expandByScalar(0.5)).map((corner) => corner.project(camera));

  it("keeps the whole room and a margin around it inside the shadow map", () => {
    for (const point of projected) {
      for (const axis of [point.x, point.y, point.z]) expect(Math.abs(axis)).toBeLessThanOrEqual(1 + 1e-9);
    }
  });

  it("frames the room tightly instead of a fixed seventy-metre square", () => {
    expect(Math.max(...projected.map((point) => Math.abs(point.x)))).toBeCloseTo(1, 6);
    expect(Math.max(...projected.map((point) => Math.abs(point.y)))).toBeCloseTo(1, 6);
    expect(rig.right - rig.left).toBeLessThan(10);
  });

  it("puts a raised point and the floor a quarter of its height to the east on the same texel", () => {
    const raised = new Vector3(0.5, 1, 0.5).project(camera);
    const shadow = new Vector3(0.5 + Math.tan((15 * Math.PI) / 180), 0, 0.5).project(camera);
    expect(raised.x).toBeCloseTo(shadow.x, 6);
    expect(raised.y).toBeCloseTo(shadow.y, 6);
    expect(raised.z).toBeLessThan(shadow.z);
  });

  it("biases depth by a few millimetres of room, however deep the frame", () => {
    expect(rig.bias * (rig.far - rig.near)).toBeCloseTo(-0.004, 9);
  });
});

describe("the shadow map's resolution", () => {
  const texelsPerMetre = (rig: ReturnType<typeof shadowRig>) => rig.mapSize[0] / (rig.right - rig.left);

  it("spends its longest side on a large room and keeps every texel square", () => {
    const hall = new Box3(new Vector3(-15, 0, -6), new Vector3(15, 3, 6));
    const rig = shadowRig(hall, 0.05);
    expect(Math.max(...rig.mapSize)).toBe(2048);
    expect(rig.mapSize[1] / (rig.top - rig.bottom)).toBeCloseTo(texelsPerMetre(rig), 0);
  });

  it("stops at about four millimetres a texel in a small room instead of a needlessly large map", () => {
    const booth = new Box3(new Vector3(-1.5, 0, -1.5), new Vector3(1.5, 2.5, 1.5));
    const rig = shadowRig(booth, 0.05);
    expect(texelsPerMetre(rig)).toBeCloseTo(256, 0);
    expect(Math.max(...rig.mapSize)).toBeLessThan(2048);
  });

  it("gives a shadow's edge the same softness in metres in a small room and a large one", () => {
    for (const room of [new Box3(new Vector3(-1, 0, -1), new Vector3(1, 2, 1)), new Box3(new Vector3(-20, 0, -20), new Vector3(20, 3, 20))]) {
      const rig = shadowRig(room, 0.05);
      expect(rig.radius / texelsPerMetre(rig)).toBeCloseTo(0.025, 3);
    }
  });
});
