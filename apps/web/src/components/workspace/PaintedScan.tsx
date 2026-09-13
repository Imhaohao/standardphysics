"use client";

import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import { Mesh, MeshBasicMaterial } from "three";

/**
 * The captured surface with the colour the photos gave it.
 *
 * Colour rides on the vertices, already the brightness the room was, so the
 * material is unlit: lighting it a second time would double the shadows that
 * are in the photographs. Nothing here can be picked or dragged, because the
 * scan is one piece of geometry and the graph is what owns objects.
 */
export function PaintedScan({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const painted = useMemo(() => {
    const copy = scene.clone(true);
    copy.traverse((object) => {
      if (!(object instanceof Mesh)) return;
      object.material = new MeshBasicMaterial({ vertexColors: true });
      object.raycast = () => null;
    });
    return copy;
  }, [scene]);
  useEffect(() => () => {
    painted.traverse((object) => {
      if (object instanceof Mesh) (object.material as MeshBasicMaterial).dispose();
    });
  }, [painted]);
  return <primitive object={painted} />;
}
