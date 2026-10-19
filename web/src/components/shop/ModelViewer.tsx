"use client";

import { Edges, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import { CanvasTexture, DoubleSide, Shape, SRGBColorSpace } from "three";
import type { PlanPin } from "@/lib/plan/inkPlan";
import { modelFraming, objectBoxes, wallBoxes, type ModelBox } from "@/lib/scene/model";
import type { Scene } from "@/lib/scene/types";

export interface ModelPalette {
  paper: string;
  sheet: string;
  ink: string;
  faint: string;
  accent: string;
  status: Record<PlanPin["status"], string>;
}

interface ModelViewerProps {
  scene: Scene;
  palette: ModelPalette;
  pins: readonly PlanPin[];
  pinHeights: ReadonlyMap<string, number>;
  selectedPinId: string | null;
  onSelectPin: (pinId: string) => void;
}

function Box({ box, fill, edge, opacity = 1 }: { box: ModelBox; fill: string; edge: string; opacity?: number }) {
  return (
    <mesh position={box.center} rotation={[0, box.rotationY, 0]}>
      <boxGeometry args={box.size} />
      <meshStandardMaterial color={fill} roughness={1} transparent={opacity < 1} opacity={opacity} />
      <Edges color={edge} threshold={15} />
    </mesh>
  );
}

function Floor({ scene, palette }: { scene: Scene; palette: ModelPalette }) {
  const shapes = useMemo(
    () =>
      scene.rooms
        .filter((room) => room.floor.points.length >= 3)
        .map((room) => {
          const shape = new Shape();
          room.floor.points.forEach((point, index) => (index === 0 ? shape.moveTo(point.x, -point.y) : shape.lineTo(point.x, -point.y)));
          return { id: room.id, shape };
        }),
    [scene],
  );
  return shapes.map(({ id, shape }) => (
    <mesh key={id} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
      <shapeGeometry args={[shape]} />
      <meshStandardMaterial color={palette.sheet} side={DoubleSide} roughness={1} />
      <Edges color={palette.faint} />
    </mesh>
  ));
}

const PIN_TEXTURE_PX = 128;

function pinTexture(label: string, ring: string, palette: ModelPalette) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = PIN_TEXTURE_PX;
  const context = canvas.getContext("2d")!;
  const middle = PIN_TEXTURE_PX / 2;
  context.beginPath();
  context.arc(middle, middle, middle - 10, 0, Math.PI * 2);
  context.fillStyle = palette.paper;
  context.fill();
  context.lineWidth = 10;
  context.strokeStyle = ring;
  context.stroke();
  context.fillStyle = palette.ink;
  context.font = `600 56px ${getComputedStyle(document.body).fontFamily}`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(label, middle, middle + 3);
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

function Pin({ pin, height, color, palette, selected, onSelect }: { pin: PlanPin; height: number; color: string; palette: ModelPalette; selected: boolean; onSelect: () => void }) {
  const ring = selected ? palette.accent : color;
  const texture = useMemo(() => pinTexture(pin.label, ring, palette), [pin.label, ring, palette]);
  useEffect(() => () => texture.dispose(), [texture]);
  const size = selected ? 0.42 : 0.32;
  return (
    <group position={[pin.at.x, height, pin.at.y]}>
      <mesh position={[0, 0.25, 0]}>
        <cylinderGeometry args={[0.008, 0.008, 0.5, 6]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <sprite
        position={[0, 0.55, 0]}
        scale={[size, size, size]}
        onClick={(event) => {
          event.stopPropagation();
          onSelect();
        }}
      >
        <spriteMaterial map={texture} depthTest={false} transparent />
      </sprite>
    </group>
  );
}

/** The scanned shop as a drafting model: paper-white walls and furniture with inked edges, findings pinned above. */
export default function ModelViewer({ scene, palette, pins, pinHeights, selectedPinId, onSelectPin }: ModelViewerProps) {
  const walls = useMemo(() => wallBoxes(scene), [scene]);
  const objects = useMemo(() => objectBoxes(scene), [scene]);
  const pinned = useMemo(() => new Map(pins.map((pin) => [pin.id, pin])), [pins]);
  const { target, radius } = modelFraming(scene);
  const distance = radius * 2.4;
  return (
    <Canvas camera={{ position: [target[0] + distance * 0.7, distance * 0.9, target[2] + distance * 0.7], fov: 35, near: 0.05, far: 200 }} dpr={[1, 2]} frameloop="demand">
      <color attach="background" args={[palette.paper]} />
      <ambientLight intensity={1.6} />
      <directionalLight position={[4, 10, 6]} intensity={1.1} />
      <Floor scene={scene} palette={palette} />
      {walls.map((box) => (
        <Box key={box.id} box={box} fill={palette.sheet} edge={palette.ink} opacity={0.92} />
      ))}
      {objects.map((box) => {
        const pin = pinned.get(box.id);
        return <Box key={box.id} box={box} fill={pin ? palette.status[pin.status] : palette.paper} edge={palette.ink} opacity={pin ? 0.35 : 1} />;
      })}
      {pins.map((pin) => (
        <Pin key={pin.id} pin={pin} height={pinHeights.get(pin.id) ?? 1} color={palette.status[pin.status]} palette={palette} selected={pin.id === selectedPinId} onSelect={() => onSelectPin(pin.id)} />
      ))}
      <OrbitControls target={[...target]} enableDamping maxPolarAngle={Math.PI / 2.05} minDistance={radius * 0.6} maxDistance={radius * 6} makeDefault />
    </Canvas>
  );
}
