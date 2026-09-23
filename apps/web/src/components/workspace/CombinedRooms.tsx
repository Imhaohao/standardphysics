"use client";

import { Suspense } from "react";
import { IDENTITY_PLACEMENT, roomMeshPose, type RoomGroup, type RoomPlacement } from "@/lib/room-groups";
import { PaintedScan } from "./PaintedScan";

/**
 * Every walk of a floor as the photographs found it, standing where its boxes stand.
 *
 * Four walks can only be fitted together by somebody who recognises them, and
 * the boxes give nothing to recognise: white, featureless, and one room much
 * like another. Each walk was uploaded as its own scan and photographed onto
 * its mesh, so what gets dragged here is the shelving and the signage rather
 * than a cluster of blocks.
 *
 * A walk still on its way, or one never photographed, simply does not draw. Its
 * boxes are underneath and keep it draggable, so a missing mesh costs detail
 * and never the ability to place the room.
 */
export function CombinedRooms({
  rooms,
  placements,
}: {
  rooms: RoomGroup[];
  placements: Record<string, RoomPlacement>;
}) {
  return (
    <group>
      {rooms.map((room) => {
        if (!room.scan_glb_url) return null;
        const { position, yaw } = roomMeshPose(placements[room.name] ?? IDENTITY_PLACEMENT);
        return (
          <group key={room.name} position={position} rotation={[0, -yaw, 0]}>
            <Suspense fallback={null}>
              <PaintedScan url={room.scan_glb_url} />
            </Suspense>
          </group>
        );
      })}
    </group>
  );
}
