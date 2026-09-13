"use client";

import { Html } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import { useRef } from "react";
import { Plane, Vector3 } from "three";
import type { StopMarker } from "@/lib/route";
import { MODEL } from "./palette";

const FLOOR = new Plane(new Vector3(0, 1, 0), 0);

export type RouteHandles = {
  markers: StopMarker[];
  editable: boolean;
  onGrab: () => void;
  onDrag: (marker: StopMarker, dx: number, dy: number) => void;
  onDrop: () => void;
};

function useMarkerDrag(marker: StopMarker, route: RouteHandles) {
  const from = useRef<Vector3 | null>(null);
  const hit = (event: ThreeEvent<PointerEvent>) => event.ray.intersectPlane(FLOOR, new Vector3());
  if (!route.editable) return {};
  return {
    onPointerDown(event: ThreeEvent<PointerEvent>) {
      event.stopPropagation();
      (event.target as unknown as Element).setPointerCapture(event.pointerId);
      from.current = hit(event);
      route.onGrab();
    },
    onPointerMove(event: ThreeEvent<PointerEvent>) {
      const point = from.current && hit(event);
      if (!from.current || !point) return;
      route.onDrag(marker, point.x - from.current.x, -(point.z - from.current.z));
      from.current = point;
    },
    onPointerUp(event: ThreeEvent<PointerEvent>) {
      if (!from.current) return;
      (event.target as unknown as Element).releasePointerCapture(event.pointerId);
      from.current = null;
      route.onDrop();
    },
  };
}

function Marker({ marker, route }: { marker: StopMarker; route: RouteHandles }) {
  const drag = useMarkerDrag(marker, route);
  return (
    <group position={[marker.x, 0, -marker.y]}>
      <mesh position-y={0.02} rotation-x={-Math.PI / 2} {...drag}>
        <circleGeometry args={[0.28, 32]} />
        <meshBasicMaterial color={MODEL.accent} transparent opacity={route.editable ? 0.85 : 0.5} depthWrite={false} />
      </mesh>
      <Html position={[0, 0.3, 0]} center style={{ pointerEvents: "none" }}>
        <span className="whitespace-nowrap rounded-md bg-accent px-2 py-1 text-sm font-semibold text-paper shadow-md">
          {marker.label}
        </span>
      </Html>
    </group>
  );
}

export function StopMarkers({ route }: { route: RouteHandles }) {
  return (
    <group>
      {route.markers.map((marker) => (
        <Marker key={marker.key} marker={marker} route={route} />
      ))}
    </group>
  );
}
