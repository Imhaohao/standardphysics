import type { Vec3 } from "@/types/contracts";

export type ViewerPoint = [x: number, y: number, z: number];

export function toViewer(point: Vec3): ViewerPoint {
  return [point.x, point.z, -point.y];
}

export function toViewerAtHeight(point: Vec3, height: number): ViewerPoint {
  return [point.x, height, -point.y];
}
