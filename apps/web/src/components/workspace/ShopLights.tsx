"use client";

import { useThree } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import type { DirectionalLight } from "three";
import { roomBounds, shadowRig, type ShadowRig } from "@/lib/scan-shadows";
import type { SceneGraph } from "@/types/contracts";
import { SHADOW } from "./palette";

const HEMI_LIGHT_ARGS: [string, string, number] = ["#ffffff", "#d8d2c4", 1.25];
/** How far, in metres, a lit box face looks up its shadow off its own surface, so the boxes never shade themselves in stripes. */
const NORMAL_BIAS = 0.01;

/** Stands the light where the rig says and frames its shadow camera on the room. */
export function aimLight(light: DirectionalLight, rig: ShadowRig) {
  light.position.copy(rig.position);
  light.target.position.copy(rig.target);
  light.target.updateMatrixWorld();
  const { shadow } = light;
  Object.assign(shadow.camera, { left: rig.left, right: rig.right, top: rig.top, bottom: rig.bottom, near: rig.near, far: rig.far });
  shadow.camera.updateProjectionMatrix();
  shadow.mapSize.set(...rig.mapSize);
  shadow.radius = rig.radius;
  shadow.bias = rig.bias;
  shadow.normalBias = NORMAL_BIAS;
  shadow.needsUpdate = true;
}

/**
 * Soft light from all round, and one light that can cast.
 *
 * The casting light stands over the measured room and leans the same way in
 * every view, so a shadow falls the same way on the boxes as on the painted
 * scan. Its shadow camera is framed on the room the scan measured rather than
 * the layout being dragged, so a piece sliding about never reframes it.
 *
 * The light casts only while the renderer draws shadows. Turning the canvas's
 * shadows off stops the shadow map updating but leaves every material sampling
 * the last one drawn, so shadows froze in place while rooms moved. A light that
 * stops casting changes the lighting setup, and three rebuilds the materials
 * without the shadow lookup.
 */
export function ShopLights({ room, castShadow }: { room: SceneGraph; castShadow: boolean }) {
  const light = useRef<DirectionalLight>(null);
  const invalidate = useThree((state) => state.invalidate);
  const rig = useMemo(() => shadowRig(roomBounds(room), SHADOW.penumbra), [room]);
  useLayoutEffect(() => {
    if (!light.current) return;
    aimLight(light.current, rig);
    invalidate();
  }, [rig, invalidate]);
  return (
    <>
      <hemisphereLight args={HEMI_LIGHT_ARGS} />
      <directionalLight ref={light} intensity={1.25} castShadow={castShadow} />
    </>
  );
}
