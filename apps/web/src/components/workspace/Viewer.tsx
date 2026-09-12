"use client";

import { ContactShadows } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Component, Suspense, type ReactNode } from "react";
import type { ViewerPose } from "@/lib/camera";
import type { Finding, SceneGraph } from "@/types/contracts";
import { FindingAnnotation } from "./Annotation";
import { CameraRig } from "./CameraRig";
import { MODEL, outcomeColor } from "./palette";
import { type ArrangeHandlers, BoxShopModel, GlbShopModel } from "./ShopModel";

type ViewerProps = {
  scene: SceneGraph;
  exported: SceneGraph;
  arrange: ArrangeHandlers | null;
  dragging: boolean;
  glbUrl: string | null;
  pose: ViewerPose;
  selected: Finding | null;
  onSelectNode: (nodeId: string) => void;
  onClearSelection: () => void;
};

class GlbFallback extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function Lights() {
  return (
    <>
      <hemisphereLight args={["#ffffff", "#d8d2c4", 1.25]} />
      <directionalLight
        position={[3, 14, 5]}
        intensity={1.4}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-12}
        shadow-camera-right={12}
        shadow-camera-top={12}
        shadow-camera-bottom={-12}
        shadow-bias={-0.0004}
      />
    </>
  );
}

export default function Viewer({ scene, exported, arrange, dragging, glbUrl, pose, selected, onSelectNode, onClearSelection }: ViewerProps) {
  const focus = selected?.locus ? new Set(selected.locus.node_ids) : null;
  const modelProps = {
    shown: scene,
    focus,
    focusColor: selected ? outcomeColor(selected.outcome) : MODEL.accent,
    onSelectNode,
    arrange,
  };
  const boxes = <BoxShopModel {...modelProps} />;

  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      shadows
      camera={{ position: pose.position, fov: pose.fov, near: 0.05, far: 200 }}
      flat
      gl={{ antialias: true }}
      onCreated={(state) => {
        if (process.env.NODE_ENV === "development") Object.assign(window, { __viewer: state });
      }}
      onPointerMissed={onClearSelection}
      aria-label="3D model of the shop"
    >
      <color attach="background" args={["#f6f5f1"]} />
      <Lights />
      <CameraRig pose={pose} locked={dragging} />
      <mesh rotation-x={-Math.PI / 2} position-y={-0.002} receiveShadow>
        <planeGeometry args={[80, 80]} />
        <meshStandardMaterial color={MODEL.ground} roughness={1} />
      </mesh>
      <ContactShadows position={[0, 0.001, 0]} scale={30} opacity={0.35} blur={2.4} far={3} frames={1} />
      {glbUrl ? (
        <GlbFallback fallback={boxes}>
          <Suspense fallback={boxes}>
            <GlbShopModel url={glbUrl} exported={exported} {...modelProps} />
          </Suspense>
        </GlbFallback>
      ) : (
        boxes
      )}
      {selected && <FindingAnnotation finding={selected} />}
    </Canvas>
  );
}
