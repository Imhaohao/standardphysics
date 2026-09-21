import type { CameraPose, SceneGraph } from "@/types/contracts";
import { Box3, Vector3 } from "three";
import { toViewer, type ViewerPoint } from "./coordinates";

export type ViewerPose = { position: ViewerPoint; target: ViewerPoint; fov: number };

export const TWEEN_MS = 700;

/** Fit the measured room inside the narrower viewport angle, preserving view direction. */
export function fitPoseToBounds(pose: ViewerPose, bounds: Box3, aspect: number): ViewerPose {
  const center = bounds.getCenter(new Vector3());
  const verticalAngle = pose.fov * Math.PI / 360;
  const direction = new Vector3(...pose.position).sub(new Vector3(...pose.target)).normalize();
  const right = new Vector3(0, 1, 0).cross(direction).normalize();
  const up = direction.clone().cross(right);
  let distance = 0.1;
  for (const x of [bounds.min.x, bounds.max.x]) {
    for (const y of [bounds.min.y, bounds.max.y]) {
      for (const z of [bounds.min.z, bounds.max.z]) {
        const offset = new Vector3(x, y, z).sub(center);
        const depth = offset.dot(direction);
        distance = Math.max(distance, depth + Math.abs(offset.dot(right)) / (Math.tan(verticalAngle) * aspect),
          depth + Math.abs(offset.dot(up)) / Math.tan(verticalAngle));
      }
    }
  }
  return {
    position: center.clone().addScaledVector(direction, distance * 1.1).toArray() as ViewerPoint,
    target: center.toArray() as ViewerPoint,
    fov: pose.fov,
  };
}

export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3);
}

export function poseFromLocus(camera: CameraPose): ViewerPose {
  return { position: toViewer(camera.position), target: toViewer(camera.target), fov: camera.fov_degrees };
}

/**
 * How far the camera may sit from the floor, and what it can still see there.
 *
 * These were fixed at five centimetres and two hundred metres, which suits one
 * room and nothing larger. Four walks of a library floor laid side by side are
 * a hundred and twenty metres across, so the far plane cut the far half of the
 * floor away and pulling back to see all of it made everything vanish at once.
 * Both ends follow the size of what is being looked at instead.
 */
export function clipPlanes(scene: SceneGraph) {
  const { span } = footprintBounds(scene);
  return { near: Math.max(0.05, span / 2000), far: Math.max(200, span * 8) };
}

/** Close enough to read a chair, far enough back to hold the whole floor. */
export function zoomRange(scene: SceneGraph) {
  const { span } = footprintBounds(scene);
  return { min: 0.5, max: span * 3 };
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
