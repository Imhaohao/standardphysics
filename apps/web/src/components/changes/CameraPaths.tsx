"use client";

import { Line } from "@react-three/drei";
import { useMemo } from "react";
import { type Color, Vector3 } from "three";
import { type ChangeCamera, type Video, cameraPath } from "@/lib/room-changes";

const GLYPH_DEPTH_M = 0.16;
const GLYPH_EVERY = 4;

/** A small pyramid for one filmed frame, pointing the way the phone faced. Rotations use x right, y down, z ahead. */
function glyphSegments(camera: ChangeCamera): Vector3[] {
  const r = camera.rotation;
  const toWorld = (x: number, y: number, z: number) => new Vector3(
    camera.position[0] + r[0] * x + r[1] * y + r[2] * z,
    camera.position[1] + r[3] * x + r[4] * y + r[5] * z,
    camera.position[2] + r[6] * x + r[7] * y + r[8] * z,
  );
  const halfHeight = Math.tan((camera.fov_y_deg * Math.PI) / 360) * GLYPH_DEPTH_M;
  const halfWidth = halfHeight * camera.aspect;
  const apex = toWorld(0, 0, 0);
  const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([x, y]) => toWorld(x * halfWidth, y * halfHeight, GLYPH_DEPTH_M));
  return corners.flatMap((corner, i) => [apex, corner, corner, corners[(i + 1) % 4]]);
}

function Walk({ cameras, video, colour }: { cameras: ChangeCamera[]; video: Video; colour: Color }) {
  const path = useMemo(() => cameraPath(cameras, video).map((p) => new Vector3(...p)), [cameras, video]);
  const glyphs = useMemo(() => cameras.filter((camera) => camera.video === video)
    .filter((_, index) => index % GLYPH_EVERY === 0).flatMap(glyphSegments), [cameras, video]);
  if (path.length < 2) return null;
  return (
    <group>
      <Line points={path} color={colour} lineWidth={1.5} dashed={video === "before"} dashSize={0.08} gapSize={0.06} />
      <Line points={glyphs} segments color={colour} lineWidth={1} />
    </group>
  );
}

/** Where each phone walked, so a blind spot can be read against the path that missed it. */
export function CameraPaths({ cameras, before, after, colour }: {
  cameras: ChangeCamera[]; before: boolean; after: boolean; colour: Color;
}) {
  return (
    <group>
      {before && <Walk cameras={cameras} video="before" colour={colour} />}
      {after && <Walk cameras={cameras} video="after" colour={colour} />}
    </group>
  );
}
