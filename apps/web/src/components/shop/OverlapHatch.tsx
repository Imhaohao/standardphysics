"use client";

import { useFrame } from "@react-three/fiber";
import { useRef, useState } from "react";
import { ShaderMaterial } from "three";
import type { ThemeColors } from "@/lib/themeColors";
import { counterLayout } from "./counterLayout";
import { useStageLevels } from "./stageLevels";

const SKIN = 0.008;
const FRONT_OVERHANG = 0.03;
const { high, low, centerZ, depth } = counterLayout;
const excessHeight = high.topY - low.topY;
const excessLength = high.eastX - high.westX;

const vertexShader = /* glsl */ `
  varying vec3 vWorld;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorld = world.xyz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying vec3 vWorld;
  void main() {
    float stripe = step(0.55, fract((vWorld.x + vWorld.y - vWorld.z) * 28.0));
    gl_FragColor = vec4(uColor, mix(0.16, 0.92, stripe) * uOpacity);
    #include <colorspace_fragment>
  }
`;

export function OverlapHatch({ colors }: { colors: ThemeColors }) {
  const levels = useStageLevels();
  const material = useRef<ShaderMaterial>(null);
  const [uniforms] = useState(() => ({ uColor: { value: colors.fail }, uOpacity: { value: 0 } }));

  useFrame(() => {
    if (!material.current) return;
    const stillTooHigh = 1 - levels.readerMoved;
    material.current.uniforms.uOpacity.value = levels.presence * levels.focusOnCounter * levels.measuring * stillTooHigh;
  });

  return (
    <mesh
      position={[(high.westX + high.eastX) / 2, low.topY + excessHeight / 2 + SKIN / 2, centerZ + FRONT_OVERHANG / 2]}
      scale={[excessLength + SKIN * 2, excessHeight + SKIN, depth + FRONT_OVERHANG + SKIN * 2]}
      renderOrder={4}
    >
      <boxGeometry args={[1, 1, 1]} />
      <shaderMaterial
        ref={material}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}
