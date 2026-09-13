"use client";

import { useFrame } from "@react-three/fiber";
import { easing } from "maath";
import { useRef, useState, type RefObject } from "react";
import { DoubleSide, Group, ShaderMaterial } from "three";
import { room } from "@/lib/fixtureShop";
import type { ThemeColors } from "@/lib/themeColors";
import { useStageLevels } from "./stageLevels";
import type { StageLevels } from "./shots";
import { sweepFrontZ } from "./sweep";

const CURTAIN_HEIGHT = 1.9;
const WAKE_DEPTH = 1.4;
const SWEEP_WIDTH = room.width + 0.9;

function isMidSweep(progress: number) {
  return progress > 0.001 && progress < 0.999;
}

function activeSweepProgress(levels: StageLevels) {
  if (isMidSweep(levels.solidified)) return levels.solidified;
  if (isMidSweep(levels.pointsRevealed)) return levels.pointsRevealed;
  return null;
}

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const curtainFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uIntensity;
  varying vec2 vUv;
  void main() {
    float fade = pow(1.0 - vUv.y, 2.2);
    float edges = smoothstep(0.0, 0.08, vUv.x) * smoothstep(1.0, 0.92, vUv.x);
    gl_FragColor = vec4(uColor, fade * edges * 0.5 * uIntensity);
    #include <colorspace_fragment>
  }
`;

const wakeFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uIntensity;
  varying vec2 vUv;
  void main() {
    float fade = pow(vUv.y, 3.0);
    float edges = smoothstep(0.0, 0.08, vUv.x) * smoothstep(1.0, 0.92, vUv.x);
    float line = smoothstep(0.965, 1.0, vUv.y);
    gl_FragColor = vec4(uColor, (fade * 0.35 + line * 0.9) * edges * uIntensity);
    #include <colorspace_fragment>
  }
`;

type SweepSheetProps = {
  fragmentShader: string;
  colors: ThemeColors;
  materialRef: RefObject<ShaderMaterial | null>;
};

function SweepSheetMaterial({ fragmentShader, colors, materialRef }: SweepSheetProps) {
  const [uniforms] = useState(() => ({ uColor: { value: colors.tapeDeep }, uIntensity: { value: 0 } }));
  return (
    <shaderMaterial
      ref={materialRef}
      vertexShader={vertexShader}
      fragmentShader={fragmentShader}
      uniforms={uniforms}
      transparent
      depthWrite={false}
      side={DoubleSide}
    />
  );
}

export function SweepLight({ colors }: { colors: ThemeColors }) {
  const levels = useStageLevels();
  const group = useRef<Group>(null);
  const intensity = useRef({ value: 0 });
  const curtain = useRef<ShaderMaterial>(null);
  const wake = useRef<ShaderMaterial>(null);

  useFrame((_, delta) => {
    const progress = activeSweepProgress(levels);
    easing.damp(intensity.current, "value", progress === null ? 0 : levels.presence, 0.18, delta);
    for (const sheet of [curtain.current, wake.current]) {
      if (sheet) sheet.uniforms.uIntensity.value = intensity.current.value;
    }
    if (group.current && progress !== null) group.current.position.z = sweepFrontZ(progress);
  });

  return (
    <group ref={group}>
      <mesh position={[0, CURTAIN_HEIGHT / 2, 0]} renderOrder={3}>
        <planeGeometry args={[SWEEP_WIDTH, CURTAIN_HEIGHT]} />
        <SweepSheetMaterial fragmentShader={curtainFragment} colors={colors} materialRef={curtain} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.012, WAKE_DEPTH / 2]} renderOrder={3}>
        <planeGeometry args={[SWEEP_WIDTH, WAKE_DEPTH]} />
        <SweepSheetMaterial fragmentShader={wakeFragment} colors={colors} materialRef={wake} />
      </mesh>
    </group>
  );
}
