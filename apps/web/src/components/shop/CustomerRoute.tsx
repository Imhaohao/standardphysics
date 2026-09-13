"use client";

import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type ComponentRef } from "react";
import { CatmullRomCurve3, Material, Vector3 } from "three";
import scenario from "@fixtures/shop.scenario.json";
import { aisleCenterX } from "@/lib/fixtureShop";
import type { ThemeColors } from "@/lib/themeColors";
import { cardReaderSpots, counterLayout } from "./counterLayout";
import { useStageLevels } from "./stageLevels";

const ROUTE_HEIGHT = 0.03;

function stopPosition(name: string) {
  const stop = scenario.stops.find((candidate) => candidate.name === name);
  if (!stop) throw new Error(`The fixture scenario has no ${name} stop`);
  return new Vector3(stop.position.x, ROUTE_HEIGHT, -stop.position.y);
}

const COUNTER_APPROACH_GAP = 0.45;

function buildRoute() {
  const entrance = stopPosition("Entrance");
  const lowCounter = new Vector3(cardReaderSpots.onLowCounter.x, ROUTE_HEIGHT, counterLayout.frontZ + COUNTER_APPROACH_GAP);
  const curve = new CatmullRomCurve3([
    entrance,
    new Vector3(aisleCenterX, ROUTE_HEIGHT, entrance.z * 0.45),
    new Vector3(aisleCenterX, ROUTE_HEIGHT, 0),
    new Vector3((aisleCenterX + lowCounter.x) / 2, ROUTE_HEIGHT, lowCounter.z * 0.55),
    lowCounter,
  ]);
  const points = curve.getPoints(120);
  return { points, length: curve.getLength(), entrance, counter: lowCounter };
}

function RouteStop({ position, color }: { position: Vector3; color: ThemeColors["ink"] }) {
  const levels = useStageLevels();
  const material = useRef<Material>(null);

  useFrame(() => {
    if (!material.current) return;
    material.current.opacity = levels.presence * Math.min(levels.route * 3, 1);
  });

  return (
    <mesh position={position} rotation-x={-Math.PI / 2}>
      <ringGeometry args={[0.07, 0.13, 40]} />
      <meshBasicMaterial ref={material} color={color} transparent opacity={0} />
    </mesh>
  );
}

export function CustomerRoute({ colors }: { colors: ThemeColors }) {
  const levels = useStageLevels();
  const line = useRef<ComponentRef<typeof Line>>(null);
  const route = useMemo(() => buildRoute(), []);

  useFrame(() => {
    if (!line.current) return;
    const material = line.current.material;
    material.dashOffset = route.length * (1 - levels.route);
    material.opacity = levels.presence;
    material.visible = levels.route > 0.001;
  });

  return (
    <group>
      <Line
        ref={line}
        points={route.points}
        color={colors.ink}
        lineWidth={4}
        dashed
        dashSize={route.length}
        gapSize={route.length}
        transparent
      />
      <RouteStop position={route.entrance} color={colors.ink} />
      <RouteStop position={route.counter} color={colors.pass} />
    </group>
  );
}
