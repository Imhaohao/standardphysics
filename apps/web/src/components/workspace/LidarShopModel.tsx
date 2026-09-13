"use client";

import { useEffect, useMemo, useState } from "react";
import { Html } from "@react-three/drei";
import { Box3 } from "three";
import { lidarGeometry, lidarMatrix, objectAtPoint, validateLidarMesh } from "@/lib/lidar-mesh";
import type { LidarMesh, SceneGraph } from "@/types/contracts";
import { MODEL } from "./palette";

export function LidarShopModel({ url, scene, onSelectNode, onBounds, interactive = true }: {
  url: string; scene: SceneGraph; onSelectNode: (id: string) => void; onBounds: (bounds: Box3) => void; interactive?: boolean;
}) {
  const [mesh, setMesh] = useState<LidarMesh | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error("Scan surfaces unavailable");
        const loaded = validateLidarMesh(await response.json());
        if (!controller.signal.aborted) setMesh(loaded);
      } catch {
        if (!controller.signal.aborted) setFailed(true);
      }
    }
    void load();
    return () => controller.abort();
  }, [url]);
  if (failed) return interactive ? <ScanMessage alert text="Reload the page to try loading the scanned surfaces again." /> : null;
  if (!mesh) return interactive ? <ScanMessage text="Loading scanned surfaces" /> : null;
  return <MeasuredSurfaces mesh={mesh} scene={scene} onSelectNode={onSelectNode} onBounds={onBounds} interactive={interactive} />;
}

function ScanMessage({ text, alert = false }: { text: string; alert?: boolean }) {
  return <Html center calculatePosition={(_, __, size) => [size.width / 2, size.height / 2]}>
    <p role={alert ? "alert" : "status"} className="w-64 rounded-lg bg-sheet p-4 text-center text-ink">{text}</p>
  </Html>;
}

function MeasuredSurfaces({ mesh, scene, onSelectNode, onBounds, interactive }: {
  mesh: LidarMesh; scene: SceneGraph; onSelectNode: (id: string) => void; onBounds: (bounds: Box3) => void; interactive: boolean;
}) {
  const parts = useMemo(() => mesh.parts.map((part) => ({
    id: part.id, geometry: lidarGeometry(part), matrix: lidarMatrix(part, mesh.floorY ?? 0),
  })), [mesh]);
  useEffect(() => () => { parts.forEach((part) => part.geometry.dispose()); }, [parts]);
  useEffect(() => {
    const bounds = new Box3();
    for (const part of parts) {
      part.geometry.computeBoundingBox();
      bounds.union(part.geometry.boundingBox!.clone().applyMatrix4(part.matrix));
    }
    onBounds(bounds);
  }, [parts, onBounds]);
  return <group>{parts.map((part) => (
    <mesh key={part.id} geometry={part.geometry} matrix={part.matrix} matrixAutoUpdate={false}
      raycast={interactive ? undefined : () => null}
      onClick={interactive ? (event) => {
        event.stopPropagation();
        onSelectNode(objectAtPoint(scene, event.point)?.id ?? "");
      } : undefined}>
      <meshStandardMaterial color={MODEL.ground} roughness={0.9} transparent={!interactive} opacity={interactive ? 1 : 0.2} depthWrite={interactive} />
    </mesh>
  ))}</group>;
}
