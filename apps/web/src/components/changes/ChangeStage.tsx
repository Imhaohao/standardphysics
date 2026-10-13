"use client";

import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Color, Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { easeOutCubic, TWEEN_MS } from "@/lib/camera";
import {
  CHANGE_TOKEN, type ChangeScene, type Cloud, type RoomChange, type Vec3, changeCentre, changeReach,
} from "@/lib/room-changes";
import { CameraPaths } from "./CameraPaths";
import { ChangeCloud, type CloudView } from "./ChangeCloud";
import { ChangeMark } from "./ChangeMarks";
import { FurnitureNames } from "./FurnitureNames";

export type Shot = { position: Vec3; target: Vec3; key: string };

function token(name: string): Color {
  return new Color(getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888888");
}

function usePalette(changes: RoomChange[]) {
  return useMemo(() => ({
    tints: changes.map((change) => token(CHANGE_TOKEN[change.type])),
    moved: changes.map((change) => change.type === "moved"),
    hatch: token("--color-unseen"),
    paper: token("--color-paper"),
    ink: token("--color-ink-muted"),
  }), [changes]);
}

/** Looking over the start of the before video's shoulder, high enough to see the whole floor. */
export function overviewShot(scene: ChangeScene): Shot {
  const { low, high } = scene.room;
  const centre: Vec3 = [(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, 0.4];
  const span = Math.max(high[0] - low[0], high[1] - low[1]);
  const start = scene.cameras.find((camera) => camera.video === "before")?.position ?? [centre[0], low[1], 1.5];
  const away = new Vector3(start[0] - centre[0], start[1] - centre[1], 0).normalize();
  const position: Vec3 = [centre[0] + away.x * span * 0.75, centre[1] + away.y * span * 0.75, span * 0.95];
  return { position, target: centre, key: "overview" };
}

/** Closer in on one change, keeping the angle the viewer is already looking from. */
export function changeShot(change: RoomChange, from: Vector3, around: Vector3): Shot {
  const target = changeCentre(change);
  const direction = from.clone().sub(around).normalize();
  const distance = Math.min(6, Math.max(1.8, changeReach(change) * 3.4));
  const position: Vec3 = [target[0] + direction.x * distance, target[1] + direction.y * distance,
    Math.max(target[2] + direction.z * distance, 1.2)];
  return { position, target, key: change.id };
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function ShotRig({ shot }: { shot: Shot }) {
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls) as OrbitControlsImpl | null;
  const tween = useRef<{ from: [Vector3, Vector3]; to: [Vector3, Vector3]; startedAt: number } | null>(null);

  useEffect(() => {
    if (!controls) return;
    const to: [Vector3, Vector3] = [new Vector3(...shot.position), new Vector3(...shot.target)];
    if (prefersReducedMotion()) {
      camera.position.copy(to[0]);
      controls.target.copy(to[1]);
      controls.update();
      return;
    }
    tween.current = { from: [camera.position.clone(), controls.target.clone()], to, startedAt: performance.now() };
  }, [shot, camera, controls]);

  useFrame(() => {
    const current = tween.current;
    if (!current || !controls) return;
    const t = Math.min(1, (performance.now() - current.startedAt) / TWEEN_MS);
    const eased = easeOutCubic(t);
    camera.position.lerpVectors(current.from[0], current.to[0], eased);
    controls.target.lerpVectors(current.from[1], current.to[1], eased);
    controls.update();
    if (t >= 1) tween.current = null;
  });
  return null;
}

/** Hands the live camera to the page, so a change can be framed from the angle the viewer chose. */
function CameraProbe({ onReady }: { onReady: (read: () => [Vector3, Vector3]) => void }) {
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls) as OrbitControlsImpl | null;
  useEffect(() => {
    if (controls) onReady(() => [camera.position.clone(), controls.target.clone()]);
  }, [camera, controls, onReady]);
  return null;
}

type StageProps = {
  scene: ChangeScene;
  cloud: Cloud;
  view: CloudView & { paths: boolean };
  selectedId: string | null;
  shot: Shot;
  onSelect: (id: string) => void;
  onClear: () => void;
  onCamera: (read: () => [Vector3, Vector3]) => void;
};

export function ChangeStage({ scene, cloud, view, selectedId, shot, onSelect, onClear, onCamera }: StageProps) {
  const palette = usePalette(scene.changes);
  const selectedIndex = scene.changes.findIndex((change) => change.id === selectedId) + 1;
  const cutHeight = Math.min(2.2, scene.room.high[2] - 0.3);
  const first = overviewShot(scene);
  return (
    <Canvas
      camera={{ up: [0, 0, 1], fov: 45, near: 0.05, far: 80, position: first.position }}
      dpr={[1, 2]}
      onPointerMissed={onClear}
      aria-label="The room in 3D, built from both videos"
    >
      <color attach="background" args={[palette.paper]} />
      <ChangeCloud cloud={cloud} view={view} tints={palette.tints} moved={palette.moved} hatch={palette.hatch}
        paper={palette.paper} selected={selectedIndex} cutHeight={cutHeight} />
      <FurnitureNames furniture={scene.furniture ?? []} />
      {scene.changes.map((change, index) => (
        <ChangeMark key={change.id} change={change} colour={palette.tints[index]} view={view}
          selected={change.id === selectedId} dimmed={selectedId !== null && change.id !== selectedId}
          onSelect={onSelect} />
      ))}
      <CameraPaths cameras={scene.cameras} before={view.paths && view.before} after={view.paths && view.after}
        colour={palette.ink} />
      <OrbitControls makeDefault target={first.target} maxPolarAngle={Math.PI * 0.49} minDistance={0.8} maxDistance={14}
        enableDamping={false} />
      <ShotRig shot={shot} />
      <CameraProbe onReady={onCamera} />
    </Canvas>
  );
}
