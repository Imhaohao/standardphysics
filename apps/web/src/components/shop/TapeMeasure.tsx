"use client";

import { Html, RoundedBox } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Group, Mesh, MeshStandardMaterial, PlaneGeometry, Vector3 } from "three";
import { facts } from "@/lib/facts";
import type { ThemeColors } from "@/lib/themeColors";
import { metersToInches } from "@/lib/units";
import { counterLayout, counterTopUnderReader, placeCardReader } from "./counterLayout";
import { useStageLevels } from "./stageLevels";
import { createTapeTexture, TAPE_TEXTURE_INCHES } from "./tapeTexture";

const BLADE_WIDTH = 0.11;
const HOUSING_SIZE = 0.2;
const TAPE_OFFSET_X = 0.3;
const bladeZ = counterLayout.frontZ + 0.05;
const LABEL_RISE = 0.5;

function updateBladeMaterial(material: MeshStandardMaterial | null, opacity: number, lengthMeters: number) {
  if (!material) return;
  material.opacity = opacity;
  material.map?.repeat.setX(metersToInches(lengthMeters) / TAPE_TEXTURE_INCHES);
}

function updateLabelOpacity(element: HTMLDivElement | null, visible: number) {
  if (!element) return;
  element.style.opacity = String(Math.max(0, (visible - 0.6) / 0.4));
}

function MeasurementLabel({ inches }: { inches: number }) {
  const passes = inches <= facts.accessibleCounterMaxHeight.value;
  const Icon = passes ? CheckCircle : WarningCircle;
  return (
    <div
      className={`flex items-center whitespace-nowrap font-display text-headline font-extrabold figures-tabular transition-colors duration-500 ${passes ? "text-pass" : "text-fail"}`}
    >
      <Icon weight="fill" className="icon-em" aria-hidden />
      <span>{inches} in</span>
    </div>
  );
}

export function TapeMeasure({ colors }: { colors: ThemeColors }) {
  const levels = useStageLevels();
  const tape = useRef<Group>(null);
  const housing = useRef<Group>(null);
  const blade = useRef<Mesh>(null);
  const bladeMaterial = useRef<MeshStandardMaterial>(null);
  const hook = useRef<Group>(null);
  const label = useRef<Group>(null);
  const labelElement = useRef<HTMLDivElement>(null);
  const [readerSpot] = useState(() => new Vector3());
  const [inches, setInches] = useState<number>(facts.counterHeightInLawsuit.value);

  const texture = useMemo(() => createTapeTexture(), []);
  const bladeGeometry = useMemo(() => new PlaneGeometry(1, 1).translate(0.5, 0, 0).rotateZ(Math.PI / 2), []);

  useEffect(() => () => texture.dispose(), [texture]);

  useFrame(() => {
    const counterTop = counterTopUnderReader(levels.readerMoved);
    const extended = counterTop * levels.measuring;
    const visible = levels.presence * levels.measuring;
    placeCardReader(readerSpot, levels.readerMoved);

    tape.current?.position.setX(readerSpot.x + TAPE_OFFSET_X);
    housing.current?.scale.setScalar(Math.max(visible, 0.0001));
    blade.current?.scale.set(BLADE_WIDTH, Math.max(extended, 0.0001), 1);
    hook.current?.position.setY(extended);
    hook.current?.scale.setScalar(Math.max(visible, 0.0001));
    label.current?.position.set(readerSpot.x, counterTop + LABEL_RISE, counterLayout.centerZ);
    updateBladeMaterial(bladeMaterial.current, visible, extended);
    updateLabelOpacity(labelElement.current, visible);

    const measured = Math.round(metersToInches(counterTop));
    if (measured !== inches) setInches(measured);
  });

  return (
    <group>
      <group ref={tape} position={[0, 0, bladeZ]}>
        <group ref={housing}>
          <RoundedBox args={[HOUSING_SIZE, HOUSING_SIZE, 0.08]} radius={0.03} position={[0, HOUSING_SIZE / 2, 0.06]} castShadow>
            <meshStandardMaterial color={colors.tape} roughness={0.55} />
          </RoundedBox>
          <mesh position={[0, HOUSING_SIZE / 2, 0.101]}>
            <circleGeometry args={[0.055, 40]} />
            <meshBasicMaterial color={colors.ink} />
          </mesh>
        </group>
        <mesh ref={blade} geometry={bladeGeometry} scale={[BLADE_WIDTH, 0.0001, 1]} castShadow>
          <meshStandardMaterial ref={bladeMaterial} map={texture} roughness={0.45} metalness={0.05} transparent />
        </mesh>
        <group ref={hook}>
          <mesh position={[0, 0.006, -0.03]}>
            <boxGeometry args={[BLADE_WIDTH, 0.012, 0.07]} />
            <meshBasicMaterial color={colors.ink} />
          </mesh>
        </group>
      </group>
      <group ref={label}>
        <Html center zIndexRange={[5, 5]}>
          <div ref={labelElement} style={{ opacity: 0 }}>
            <MeasurementLabel inches={inches} />
          </div>
        </Html>
      </group>
    </group>
  );
}
