"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import { BufferAttribute, BufferGeometry, MathUtils, PerspectiveCamera, ShaderMaterial, Vector3 } from "three";
import type { ThemeColors } from "@/lib/themeColors";
import { shopPieces, type ShopPart, type ShopPiece } from "./shopParts";
import { useStageLevels } from "./stageLevels";
import { sweepProgressAt } from "./sweep";

const POINTS_PER_SQUARE_METER = 420;
const EDGE_POINTS_PER_METER = 150;
const EDGE_SCATTER = 0.012;
const POINT_WORLD_SIZE = 0.024;

function seededRandom(seed: number) {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Random = () => number;
type FaceSampler = { area: number; sample: (random: Random) => Vector3 };

function boxFaces(size: Vector3): FaceSampler[] {
  const { x: w, y: h, z: d } = size;
  const spread = (random: Random, extent: number) => (random() - 0.5) * extent;
  return [
    { area: w * d, sample: (r) => new Vector3(spread(r, w), h / 2, spread(r, d)) },
    { area: d * h, sample: (r) => new Vector3(w / 2, spread(r, h), spread(r, d)) },
    { area: d * h, sample: (r) => new Vector3(-w / 2, spread(r, h), spread(r, d)) },
    { area: w * h, sample: (r) => new Vector3(spread(r, w), spread(r, h), d / 2) },
    { area: w * h, sample: (r) => new Vector3(spread(r, w), spread(r, h), -d / 2) },
  ];
}

function cylinderFaces(size: Vector3): FaceSampler[] {
  const radius = size.x / 2;
  return [
    { area: Math.PI * radius * radius, sample: (r) => {
      const angle = r() * Math.PI * 2;
      const distance = Math.sqrt(r()) * radius;
      return new Vector3(Math.cos(angle) * distance, size.y / 2, Math.sin(angle) * distance);
    } },
    { area: Math.PI * size.x * size.y, sample: (r) => {
      const angle = r() * Math.PI * 2;
      return new Vector3(Math.cos(angle) * radius, (r() - 0.5) * size.y, Math.sin(angle) * radius);
    } },
  ];
}

const facesByShape = { box: boxFaces, cylinder: cylinderFaces };

function boxEdges(size: Vector3): [Vector3, Vector3][] {
  const half = size.clone().multiplyScalar(0.5);
  const corner = (sx: number, sy: number, sz: number) => new Vector3(sx * half.x, sy * half.y, sz * half.z);
  const signs = [-1, 1];
  return signs.flatMap((a) =>
    signs.flatMap((b) => [
      [corner(-1, a, b), corner(1, a, b)],
      [corner(a, -1, b), corner(a, 1, b)],
      [corner(a, b, -1), corner(a, b, 1)],
    ] as [Vector3, Vector3][]),
  );
}

function sampleEdges(shopPart: ShopPart, random: Random) {
  if (shopPart.shape !== "box") return [];
  return boxEdges(shopPart.size).flatMap(([start, end]) => {
    const count = Math.round(start.distanceTo(end) * EDGE_POINTS_PER_METER);
    return Array.from({ length: count }, () =>
      start
        .clone()
        .lerp(end, random())
        .add(new Vector3(random() - 0.5, random() - 0.5, random() - 0.5).multiplyScalar(EDGE_SCATTER)),
    );
  });
}

function samplePart(piece: ShopPiece, shopPart: ShopPart, random: Random) {
  const surfacePoints = facesByShape[shopPart.shape](shopPart.size).flatMap((face) => {
    const count = Math.max(1, Math.round(face.area * POINTS_PER_SQUARE_METER));
    return Array.from({ length: count }, () => face.sample(random));
  });
  return [...surfacePoints, ...sampleEdges(shopPart, random)].map((point) =>
    point.add(shopPart.center).applyQuaternion(piece.quaternion).add(piece.position),
  );
}

function buildPointCloud() {
  const random = seededRandom(31);
  const points = shopPieces.flatMap((piece) => piece.parts.flatMap((shopPart) => samplePart(piece, shopPart, random)));
  const positions = new Float32Array(points.length * 3);
  const sweep = new Float32Array(points.length);
  const seeds = new Float32Array(points.length);
  const drift = new Float32Array(points.length * 3);

  points.forEach((point, index) => {
    positions.set([point.x, point.y, point.z], index * 3);
    sweep[index] = MathUtils.clamp(sweepProgressAt(point.z) + (random() - 0.5) * 0.02, 0, 1);
    seeds[index] = random();
    const direction = new Vector3(random() - 0.5, random() * 0.9 + 0.2, random() - 0.5).normalize();
    drift.set([direction.x, direction.y, direction.z], index * 3);
  });

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  geometry.setAttribute("aSweep", new BufferAttribute(sweep, 1));
  geometry.setAttribute("aSeed", new BufferAttribute(seeds, 1));
  geometry.setAttribute("aDrift", new BufferAttribute(drift, 3));
  return geometry;
}

const vertexShader = /* glsl */ `
  uniform float uReveal;
  uniform float uSolid;
  uniform float uScatter;
  uniform float uPointScale;
  attribute float aSweep;
  attribute float aSeed;
  attribute vec3 aDrift;
  varying float vAlpha;
  varying float vFlash;

  const float BAND = 0.05;

  void main() {
    float revealFront = uReveal * (1.0 + BAND);
    float solidFront = uSolid * (1.0 + BAND);
    float shown = smoothstep(aSweep, aSweep + BAND * 0.3, revealFront);
    float dissolved = smoothstep(aSweep + BAND * 0.55, aSweep + BAND, solidFront);
    float revealGlow = shown * (1.0 - smoothstep(0.0, BAND * 1.5, revealFront - aSweep));
    float solidGlow = step(0.0005, uSolid) * smoothstep(aSweep - BAND, aSweep + BAND * 0.55, solidFront);
    vFlash = clamp(max(revealGlow, solidGlow), 0.0, 1.0);
    vAlpha = shown * (1.0 - dissolved);

    vec3 drifted = position + aDrift * uScatter * (2.0 + aSeed * 4.0);
    vec4 viewPosition = modelViewMatrix * vec4(drifted, 1.0);
    gl_Position = projectionMatrix * viewPosition;
    float size = (0.55 + aSeed * 0.9) * (1.0 + vFlash * 0.45);
    gl_PointSize = size * uPointScale / -viewPosition.z;
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 uInk;
  uniform vec3 uFlash;
  uniform float uPresence;
  varying float vAlpha;
  varying float vFlash;

  void main() {
    float disc = 1.0 - smoothstep(0.36, 0.5, length(gl_PointCoord - 0.5));
    float alpha = disc * vAlpha * uPresence * mix(0.62, 1.0, vFlash);
    if (alpha < 0.01) discard;
    gl_FragColor = vec4(mix(uInk, uFlash, vFlash), alpha);
    #include <colorspace_fragment>
  }
`;

export function ScanPoints({ colors }: { colors: ThemeColors }) {
  const levels = useStageLevels();
  const { camera, size, viewport } = useThree();
  const material = useRef<ShaderMaterial>(null);
  const geometry = useMemo(() => buildPointCloud(), []);
  const [uniforms] = useState(() => ({
    uReveal: { value: 0 },
    uSolid: { value: 0 },
    uScatter: { value: 1 },
    uPresence: { value: 0 },
    uPointScale: { value: 1 },
    uInk: { value: colors.ink },
    uFlash: { value: colors.tapeDeep },
  }));

  useFrame(() => {
    if (!material.current) return;
    const current = material.current.uniforms;
    const fov = MathUtils.degToRad((camera as PerspectiveCamera).fov);
    current.uPointScale.value = (POINT_WORLD_SIZE * size.height * viewport.dpr) / (2 * Math.tan(fov / 2));
    current.uReveal.value = levels.pointsRevealed;
    current.uSolid.value = levels.solidified;
    current.uScatter.value = levels.scattered;
    current.uPresence.value = levels.presence;
  });

  return (
    <points geometry={geometry} frustumCulled={false} renderOrder={2}>
      <shaderMaterial
        ref={material}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
      />
    </points>
  );
}
