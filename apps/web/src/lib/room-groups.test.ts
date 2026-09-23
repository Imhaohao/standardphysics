import { describe, expect, it } from "vitest";
import type { Mat4, SceneNode } from "@/types/contracts";
import { moveNode, roomMeshPose, type CapturePose, type RoomPlacement } from "./room-groups";

function nodeAt(x: number, y: number): SceneNode {
  return { id: "n", transform: { m: [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, 0, 0, 0, 0, 1] } as Mat4 } as SceneNode;
}

/** Where three.js draws a capture-frame point once its group takes the mesh pose. */
function drawnAt(pose: ReturnType<typeof roomMeshPose>, x: number, y: number): [number, number] {
  const threeX = x;
  const threeZ = -y;
  const cos = Math.cos(pose.yaw);
  const sin = Math.sin(pose.yaw);
  const turnedX = threeX * cos + threeZ * sin;
  const turnedZ = -threeX * sin + threeZ * cos;
  return [turnedX + pose.position[0], -(turnedZ + pose.position[2])];
}

function capturedToPlaced(capture: CapturePose, x: number, y: number): [number, number] {
  const yaw = (capture.yaw_degrees * Math.PI) / 180;
  return [Math.cos(yaw) * x - Math.sin(yaw) * y + capture.tx, Math.sin(yaw) * x + Math.cos(yaw) * y + capture.ty];
}

describe("roomMeshPose", () => {
  const capture: CapturePose = { yaw_degrees: -58, tx: 27.85, ty: 15.47 };
  const drag: RoomPlacement = { yawDegrees: 30, tx: 2, ty: -1, cx: 25, cy: 14 };

  it("draws a walk's mesh on top of its boxes, whatever the capture and the drag", () => {
    for (const [x, y] of [[0, 0], [4, 0], [1.5, -3]]) {
      const [placedX, placedY] = capturedToPlaced(capture, x, y);
      const box = moveNode(nodeAt(placedX, placedY), drag).transform.m;
      const [meshX, meshY] = drawnAt(roomMeshPose(drag, capture), x, y);
      expect(meshX).toBeCloseTo(box[3], 9);
      expect(meshY).toBeCloseTo(box[7], 9);
    }
  });

  it("turns the mesh the same way as the boxes", () => {
    const turn: RoomPlacement = { yawDegrees: 90, tx: 0, ty: 0, cx: 0, cy: 0 };
    const [meshX, meshY] = drawnAt(roomMeshPose(turn), 1, 0);
    expect(meshX).toBeCloseTo(0, 9);
    expect(meshY).toBeCloseTo(1, 9);
  });
});
