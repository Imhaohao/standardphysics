import { Matrix4, Quaternion, Vector3 } from "three";
import sceneGraph from "@fixtures/shop.scene_graph.json";

type NodeKind = "wall" | "door" | "window" | "opening" | "floor" | "object";

type SceneGraphNode = {
  id: string;
  kind: string;
  label: string;
  dimensions: { x: number; y: number; z: number };
  transform: { m: number[] };
  movable: boolean;
};

export type ShopBox = {
  id: string;
  kind: NodeKind;
  label: string;
  movable: boolean;
  position: Vector3;
  quaternion: Quaternion;
  size: Vector3;
};

const SCENE_GRAPH_Z_UP_TO_Y_UP = new Matrix4().set(
  1, 0, 0, 0,
  0, 0, 1, 0,
  0, -1, 0, 0,
  0, 0, 0, 1,
);

const Y_UP_TO_SCENE_GRAPH_Z_UP = SCENE_GRAPH_Z_UP_TO_Y_UP.clone().invert();

function toShopBox(node: SceneGraphNode): ShopBox {
  const [a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p] = node.transform.m;
  const zUpTransform = new Matrix4().set(a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p);
  const yUpTransform = SCENE_GRAPH_Z_UP_TO_Y_UP.clone()
    .multiply(zUpTransform)
    .multiply(Y_UP_TO_SCENE_GRAPH_Z_UP);

  const position = new Vector3();
  const quaternion = new Quaternion();
  yUpTransform.decompose(position, quaternion, new Vector3());

  const { x, y, z } = node.dimensions;
  return {
    id: node.id,
    kind: node.kind as NodeKind,
    label: node.label,
    movable: node.movable,
    position,
    quaternion,
    size: new Vector3(x, z, y),
  };
}

export const shopBoxes: ShopBox[] = (sceneGraph.nodes as SceneGraphNode[]).map(toShopBox);

function boxesOfKind(kind: NodeKind) {
  return shopBoxes.filter((box) => box.kind === kind);
}

export const floor = boxesOfKind("floor")[0];
export const walls = boxesOfKind("wall");
export const doors = boxesOfKind("door");
export const furniture = boxesOfKind("object");

function displayCaseAisleCenterX() {
  const cases = furniture
    .filter((box) => box.label === "Display case")
    .sort((left, right) => left.position.x - right.position.x);
  const westInnerFace = cases[0].position.x + cases[0].size.x / 2;
  const eastInnerFace = cases[cases.length - 1].position.x - cases[cases.length - 1].size.x / 2;
  return (westInnerFace + eastInnerFace) / 2;
}

export const aisleCenterX = displayCaseAisleCenterX();

export const orderingCounter = furniture.find((box) => box.label === "Ordering counter") as ShopBox;

export const room = {
  width: floor.size.x,
  depth: floor.size.z,
};
