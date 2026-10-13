"use client";

import { Html } from "@react-three/drei";
import type { ChangeScene } from "@/lib/room-changes";

/** The unchanged furniture the sentences point to, named quietly where it stands. */
export function FurnitureNames({ furniture }: { furniture: ChangeScene["furniture"] }) {
  return (
    <group>
      {furniture.map((piece, index) => {
        const { center, size } = piece.box;
        return (
          <Html key={`${piece.name}-${index}`} position={[center[0], center[1], center[2] + size[2] / 2 + 0.05]} center
            zIndexRange={[10, 0]} className="pointer-events-none">
            <span className="hidden whitespace-nowrap rounded bg-paper/70 px-1.5 py-0.5 text-sm text-ink-muted sm:inline">
              {piece.name}
            </span>
          </Html>
        );
      })}
    </group>
  );
}
