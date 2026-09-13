"use client";

import { useEffect, useMemo, useState } from "react";
import { lidarGeometry, lidarMatrix, validateLidarMesh } from "@/lib/lidar-mesh";
import type { LidarMesh } from "@/types/contracts";
import { MODEL } from "./palette";

/** Captured triangles are optional visual evidence; the graph owns interaction. */
export function LidarShopModel({ url }: { url: string }) {
  const [mesh, setMesh] = useState<LidarMesh | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error("Scan surfaces unavailable");
        const loaded = validateLidarMesh(await response.json());
        if (!controller.signal.aborted) setMesh(loaded);
      } catch { /* Evidence must never replace the usable reconstructed view. */ }
    }
    void load();
    return () => controller.abort();
  }, [url]);
  return mesh ? <MeasuredSurfaces mesh={mesh} /> : null;
}

function MeasuredSurfaces({ mesh }: { mesh: LidarMesh }) {
  const parts = useMemo(() => mesh.parts.map((part) => ({
    id: part.id, geometry: lidarGeometry(part), matrix: lidarMatrix(part, mesh.floorY ?? 0),
  })), [mesh]);
  useEffect(() => () => { parts.forEach((part) => part.geometry.dispose()); }, [parts]);
  return <group>{parts.map((part) => (
    <mesh key={part.id} geometry={part.geometry} matrix={part.matrix} matrixAutoUpdate={false} renderOrder={-1} raycast={() => null}>
      <meshStandardMaterial color={MODEL.ground} roughness={0.9} transparent opacity={0.1} depthWrite={false} />
    </mesh>
  ))}</group>;
}
