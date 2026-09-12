import type { CameraPose, SceneGraph } from "@/types/contracts";
import { toViewer, type ViewerPoint } from "./coordinates";

export type ViewerPose = { position: ViewerPoint; target: ViewerPoint; fov: number };

export const TWEEN_MS = 700;

export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3);
}

export function poseFromLocus(camera: CameraPose): ViewerPose {
  return { position: toViewer(camera.position), target: toViewer(camera.target), fov: camera.fov_degrees };
}

function footprintBounds(scene: SceneGraph) {
  const xs = scene.nodes.map((node) => node.transform.m[3]);
  const ys = scene.nodes.map((node) => node.transform.m[7]);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  return { cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, span: Math.max(maxX - minX, maxY - minY, 2) };
}

/** From the south-east corner and above the walls, looking at the middle of the floor. */
export function overviewPose(scene: SceneGraph): ViewerPose {
  const { cx, cy, span } = footprintBounds(scene);
  return {
    position: toViewer({ x: cx + span * 0.55, y: cy - span * 0.95, z: span * 0.95 }),
    target: toViewer({ x: cx, y: cy, z: 0 }),
    fov: 50,
  };
}

export function topDownPose(scene: SceneGraph): ViewerPose {
  const { cx, cy, span } = footprintBounds(scene);
  return {
    position: toViewer({ x: cx, y: cy - 0.001, z: span * 1.45 }),
    target: toViewer({ x: cx, y: cy, z: 0 }),
    fov: 50,
  };
}
