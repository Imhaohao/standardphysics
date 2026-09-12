"use client";

import { OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { PerspectiveCamera, Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { easeOutCubic, TWEEN_MS, type ViewerPose } from "@/lib/camera";

type Tween = { from: ViewerPose; to: ViewerPose; startedAt: number };

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function currentPose(camera: PerspectiveCamera, controls: OrbitControlsImpl): ViewerPose {
  return {
    position: camera.position.toArray() as ViewerPose["position"],
    target: controls.target.toArray() as ViewerPose["target"],
    fov: camera.fov,
  };
}

function applyPose(camera: PerspectiveCamera, controls: OrbitControlsImpl, from: ViewerPose, to: ViewerPose, t: number) {
  camera.position.lerpVectors(new Vector3(...from.position), new Vector3(...to.position), t);
  controls.target.lerpVectors(new Vector3(...from.target), new Vector3(...to.target), t);
  camera.fov = from.fov + (to.fov - from.fov) * t;
  camera.updateProjectionMatrix();
  controls.update();
}

/** Orbit controls, plus a 700 ms ease-out flight whenever the requested pose changes. */
export function CameraRig({ pose }: { pose: ViewerPose }) {
  const controls = useRef<OrbitControlsImpl>(null);
  const tween = useRef<Tween | null>(null);
  const camera = useThree((state) => state.camera) as PerspectiveCamera;
  const invalidate = useThree((state) => state.invalidate);

  useEffect(() => {
    const orbit = controls.current;
    if (!orbit) return;
    if (prefersReducedMotion()) {
      applyPose(camera, orbit, pose, pose, 1);
      invalidate();
      return;
    }
    tween.current = { from: currentPose(camera, orbit), to: pose, startedAt: performance.now() };
    orbit.enabled = false;
    invalidate();
  }, [pose, camera, invalidate]);

  useFrame(() => {
    const active = tween.current;
    const orbit = controls.current;
    if (!active || !orbit) return;
    const t = easeOutCubic((performance.now() - active.startedAt) / TWEEN_MS);
    applyPose(camera, orbit, active.from, active.to, t);
    if (t >= 1) {
      tween.current = null;
      orbit.enabled = true;
      return;
    }
    invalidate();
  });

  return <OrbitControls ref={controls} makeDefault enableDamping={false} maxPolarAngle={Math.PI / 2 - 0.05} />;
}
