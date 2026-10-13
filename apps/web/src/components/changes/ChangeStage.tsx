"use client";

import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Color, type PerspectiveCamera, Spherical, Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { easeOutCubic, TWEEN_MS } from "@/lib/camera";
import {
  CHANGE_TOKEN, type ChangeScene, type Cloud, type RoomChange, type UncheckedThing, type Vec3, changeCentre, changeReach, citedFurniture,
} from "@/lib/room-changes";
import { CameraPaths } from "./CameraPaths";
import { ChangeCloud, type CloudView } from "./ChangeCloud";
import { ChangeMark } from "./ChangeMarks";
import { FurnitureNames } from "./FurnitureNames";
import { UncheckedMarks } from "./UncheckedMarks";

/** What the camera should look at; `nonce` lets the same request be made twice. */
/** `id` names a change ("c1") or a thing only one video saw ("u1"). */
export type Focus = { kind: "overview"; nonce: number } | { kind: "item"; id: string; nonce: number };
/** Turn the camera around what it looks at: radians across, radians up, and a zoom factor. */
export type Orbit = (across: number, up: number, zoom: number) => void;
type Pose = { position: Vector3; target: Vector3 };

const OVERVIEW_TILT = 0.95;

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

/** Every corner worth keeping in frame: the changes first, then the furniture they are described against. */
function framedCorners(scene: ChangeScene): Vector3[] {
  const boxes = [
    ...scene.changes.flatMap((change) => [change.before, change.after]).flatMap((place) => (place ? [place.box] : [])),
    ...(scene.furniture ?? []).map((piece) => piece.box),
  ];
  return boxes.flatMap((box) => box.corners.map((corner) => new Vector3(...corner)));
}

/** The narrower of the two fields of view, so the fit holds on a tall phone and a wide monitor alike. */
function narrowFov(camera: PerspectiveCamera): number {
  const vertical = (camera.fov * Math.PI) / 180;
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
  return Math.min(vertical, horizontal);
}

/** Over the shoulder of the before video's first frame, far enough back to fit every change. */
function overviewPose(scene: ChangeScene, camera: PerspectiveCamera): Pose {
  const corners = framedCorners(scene);
  const target = corners.reduce((sum, corner) => sum.add(corner), new Vector3()).divideScalar(Math.max(corners.length, 1));
  const radius = Math.max(1, ...corners.map((corner) => corner.distanceTo(target)));
  const start = scene.cameras.find((item) => item.video === "before")?.position ?? [target.x, target.y - 3, 1.5];
  const away = new Vector3(start[0] - target.x, start[1] - target.y, 0).normalize();
  const direction = away.multiplyScalar(Math.cos(OVERVIEW_TILT)).setZ(Math.sin(OVERVIEW_TILT));
  const labelRoom = camera.aspect < 1 ? 1.18 : 1.06;
  const distance = (radius / Math.sin(narrowFov(camera) / 2)) * labelRoom;
  return { position: target.clone().addScaledVector(direction, distance), target };
}

/** Closer in on a spot, keeping the angle the viewer is already looking from. */
function closerPose(centre: Vec3, reach: number, cap: number, camera: PerspectiveCamera, around: Vector3): Pose {
  const target = new Vector3(...centre);
  const direction = camera.position.clone().sub(around).normalize();
  const distance = Math.min(cap, Math.max(2.4, (reach / Math.sin(narrowFov(camera) / 2)) * 1.15));
  const position = target.clone().addScaledVector(direction, distance);
  position.z = Math.max(position.z, target.z + 0.8);
  return { position, target };
}

export function changePose(change: RoomChange, camera: PerspectiveCamera, around: Vector3): Pose {
  return closerPose(changeCentre(change), changeReach(change), change.type === "moved" ? 9 : 4.5, camera, around);
}

function thingPose(thing: UncheckedThing, camera: PerspectiveCamera, around: Vector3): Pose {
  const reach = Math.max(0.4, Math.hypot(...thing.box.size) / 2);
  return closerPose(thing.box.center, reach, 4.5, camera, around);
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

type Tween = { from: Pose; to: Pose; startedAt: number };

function poseFor(focus: Focus, scene: ChangeScene, camera: PerspectiveCamera, controls: OrbitControlsImpl): Pose | null {
  if (focus.kind === "overview") return overviewPose(scene, camera);
  const change = scene.changes.find((item) => item.id === focus.id);
  if (change) return changePose(change, camera, controls.target);
  const thing = (scene.unchecked ?? []).find((item) => item.id === focus.id);
  return thing ? thingPose(thing, camera, controls.target) : null;
}

function FocusRig({ focus, scene }: { focus: Focus; scene: ChangeScene }) {
  const camera = useThree((state) => state.camera) as PerspectiveCamera;
  const controls = useThree((state) => state.controls) as OrbitControlsImpl | null;
  const tween = useRef<Tween | null>(null);
  const placed = useRef(false);

  useEffect(() => {
    if (!controls) return;
    const to = poseFor(focus, scene, camera, controls);
    if (!to) return;
    if (!placed.current || prefersReducedMotion()) {
      placed.current = true;
      camera.position.copy(to.position);
      controls.target.copy(to.target);
      controls.update();
      return;
    }
    tween.current = { from: { position: camera.position.clone(), target: controls.target.clone() }, to, startedAt: performance.now() };
  }, [focus, scene, camera, controls]);

  useFrame(() => {
    const current = tween.current;
    if (!current || !controls) return;
    const t = Math.min(1, (performance.now() - current.startedAt) / TWEEN_MS);
    const eased = easeOutCubic(t);
    camera.position.lerpVectors(current.from.position, current.to.position, eased);
    controls.target.lerpVectors(current.from.target, current.to.target, eased);
    controls.update();
    if (t >= 1) tween.current = null;
  });
  return null;
}

/** Hands the page a way to turn the camera from the keyboard. */
function KeyboardOrbit({ onReady }: { onReady: (orbit: Orbit) => void }) {
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls) as OrbitControlsImpl | null;
  useEffect(() => {
    if (!controls) return;
    onReady((across, up, zoom) => {
      const offset = camera.position.clone().sub(controls.target);
      const turn = new Spherical().setFromCartesianCoords(offset.x, offset.z, -offset.y);
      turn.theta += across;
      turn.phi = Math.min(Math.PI * 0.49, Math.max(0.15, turn.phi - up));
      turn.radius = Math.min(14, Math.max(0.8, turn.radius * zoom));
      const next = new Vector3().setFromSpherical(turn);
      camera.position.copy(controls.target).add(new Vector3(next.x, -next.z, next.y));
      controls.update();
    });
  }, [camera, controls, onReady]);
  return null;
}

type StageProps = {
  scene: ChangeScene;
  cloud: Cloud;
  view: CloudView & { paths: boolean };
  selectedId: string | null;
  readingId: string | null;
  focus: Focus;
  onSelect: (id: string) => void;
  onClear: () => void;
  onOrbit: (orbit: Orbit) => void;
};

export function ChangeStage({ scene, cloud, view, selectedId, readingId, focus, onSelect, onClear, onOrbit }: StageProps) {
  const palette = usePalette(scene.changes);
  const selectedIndex = scene.changes.findIndex((change) => change.id === selectedId) + 1;
  const cutHeight = Math.min(2.2, scene.room.high[2] - 0.3);
  return (
    <Canvas camera={{ up: [0, 0, 1], fov: 45, near: 0.05, far: 80, position: [0, -6, 5] as Vec3 }} dpr={[1, 2]}
      onPointerMissed={onClear}>
      <color attach="background" args={[palette.paper]} />
      <ChangeCloud cloud={cloud} view={view} tints={palette.tints} moved={palette.moved} hatch={palette.hatch}
        paper={palette.paper} selected={selectedIndex} cutHeight={cutHeight} />
      <FurnitureNames furniture={citedFurniture(scene)} />
      {scene.changes.map((change, index) => (
        <ChangeMark key={change.id} change={change} colour={palette.tints[index]} view={view}
          selected={change.id === selectedId} dimmed={selectedId !== null && change.id !== selectedId}
          reading={change.id === readingId} onSelect={onSelect} />
      ))}
      <UncheckedMarks things={scene.unchecked ?? []} colour={palette.hatch} before={view.before} after={view.after} />
      <CameraPaths cameras={scene.cameras} before={view.paths && view.before} after={view.paths && view.after}
        colour={palette.ink} />
      <OrbitControls makeDefault maxPolarAngle={Math.PI * 0.49} minDistance={0.8} maxDistance={14} enableDamping={false} />
      <FocusRig focus={focus} scene={scene} />
      <KeyboardOrbit onReady={onOrbit} />
    </Canvas>
  );
}
