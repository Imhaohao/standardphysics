"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import { BufferAttribute, BufferGeometry, Color, MathUtils, type PerspectiveCamera, type ShaderMaterial } from "three";
import type { Cloud } from "@/lib/room-changes";

export type CloudView = { before: boolean; after: boolean; blindSpots: boolean };

const MAX_CHANGES = 32;
const POINT_SIZE_M = 0.03;

const vertexShader = /* glsl */ `
  attribute vec3 color;
  attribute float video;
  attribute float seen;
  attribute float change;
  uniform float showBefore;
  uniform float showAfter;
  uniform float blindSpots;
  uniform float selected;
  uniform float cutHeight;
  uniform float pointScale;
  uniform vec3 tints[${MAX_CHANGES}];
  uniform float ghosts[${MAX_CHANGES}];
  uniform vec3 paper;
  varying vec3 vColor;
  varying float vUnseen;

  void main() {
    float shown = video < 0.5 ? showBefore : showAfter;
    shown *= step(position.z, cutHeight);
    vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * viewPosition;
    gl_PointSize = shown * pointScale / max(-viewPosition.z, 0.05);
    vColor = color;
    vUnseen = 0.0;
    if (change > 0.5) {
      int index = int(change + 0.5);
      bool focused = selected < 0.5 || abs(selected - change) < 0.5;
      vColor = mix(color, tints[index], focused ? 0.6 : 0.3);
      bool oldPlace = video < 0.5 && ghosts[index] > 0.5 && showAfter > 0.5;
      if (oldPlace) vColor = mix(vColor, paper, 0.55);
    } else if (seen > 1.5 && blindSpots > 0.5) {
      vUnseen = 1.0;
    }
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 hatch;
  uniform vec3 paper;
  varying vec3 vColor;
  varying float vUnseen;

  void main() {
    vec2 offset = gl_PointCoord - 0.5;
    if (dot(offset, offset) > 0.25) discard;
    vec3 colour = vColor;
    if (vUnseen > 0.5) {
      float stripe = step(mod(gl_FragCoord.x + gl_FragCoord.y, 9.0), 3.0);
      colour = mix(mix(colour, paper, 0.6), hatch, stripe * 0.8);
    }
    gl_FragColor = vec4(colour, 1.0);
  }
`;

function cloudGeometry(cloud: Cloud): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(cloud.positions, 3));
  geometry.setAttribute("color", new BufferAttribute(cloud.colors, 3, true));
  geometry.setAttribute("video", new BufferAttribute(cloud.video, 1));
  geometry.setAttribute("seen", new BufferAttribute(cloud.seen, 1));
  geometry.setAttribute("change", new BufferAttribute(cloud.change, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

type ChangeCloudProps = {
  cloud: Cloud;
  view: CloudView;
  tints: Color[];
  /** Per change, whether it moved; its old place then fades while the new one is shown too. */
  moved: boolean[];
  hatch: Color;
  paper: Color;
  selected: number;
  cutHeight: number;
};

/** The shader mixes these with the photos' own sRGB bytes, so they have to be sRGB numbers too. */
function inPhotoSpace(colour: Color): Color {
  return colour.clone().convertLinearToSRGB();
}

function slots<T>(values: T[], fill: T): T[] {
  return [fill, ...values.slice(0, MAX_CHANGES - 1), ...new Array(Math.max(0, MAX_CHANGES - 1 - values.length)).fill(fill)];
}

/** Both videos' surfaces as one point cloud, each change tinted and the blind spots hatched. */
export function ChangeCloud({ cloud, view, tints, moved, hatch, paper, selected, cutHeight }: ChangeCloudProps) {
  const geometry = useMemo(() => cloudGeometry(cloud), [cloud]);
  const material = useRef<ShaderMaterial>(null);
  const { size, viewport, camera } = useThree();
  const [uniforms] = useState(() => ({
    showBefore: { value: 1 }, showAfter: { value: 1 }, blindSpots: { value: 0 }, selected: { value: 0 },
    cutHeight: { value: cutHeight }, pointScale: { value: 1 },
    tints: { value: slots(tints.map(inPhotoSpace), new Color()) },
    ghosts: { value: slots(moved.map((isMoved) => (isMoved ? 1 : 0)), 0) },
    hatch: { value: inPhotoSpace(hatch) }, paper: { value: inPhotoSpace(paper) },
  }));

  useEffect(() => () => geometry.dispose(), [geometry]);

  useFrame(() => {
    const current = material.current?.uniforms;
    if (!current) return;
    current.showBefore.value = view.before ? 1 : 0;
    current.showAfter.value = view.after ? 1 : 0;
    current.blindSpots.value = view.blindSpots ? 1 : 0;
    current.selected.value = selected;
    const fov = MathUtils.degToRad((camera as PerspectiveCamera).fov);
    current.pointScale.value = (POINT_SIZE_M * size.height * viewport.dpr) / (2 * Math.tan(fov / 2));
  });

  return (
    <points geometry={geometry}>
      <shaderMaterial ref={material} vertexShader={vertexShader} fragmentShader={fragmentShader} uniforms={uniforms} />
    </points>
  );
}
