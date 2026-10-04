"use client";

import { Html, Line } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import { DataTexture, DoubleSide, LinearFilter, LinearMipmapLinearFilter, SRGBColorSpace } from "three";
import { pinchesToMark, pinchWords, roomPointOf } from "@/lib/clearance-map";
import { type ClearanceOverlay, STALE_OPACITY } from "./ClearancePlan";
import { type ClearancePicture, HALO_TOKEN, TIGHT_TOKEN, tokenValue } from "./useClearancePicture";

/** Metres above the floor the map lies, high enough to clear a scanned floor's ripples and low enough to read as on it. */
const LIFT = { field: 0.012, edge: 0.016, ring: 0.02 };
const RING_METERS = { inner: 0.085, outer: 0.12 };

/** The picture's pixels as a floor texture. Its rows run from the highest y down, so the texture is read upside down. */
function useFloorTexture(picture: ClearancePicture): DataTexture {
  const texture = useMemo(() => {
    const made = new DataTexture(new Uint8Array(picture.pixels.buffer), picture.width, picture.height);
    made.colorSpace = SRGBColorSpace;
    made.magFilter = LinearFilter;
    made.minFilter = LinearMipmapLinearFilter;
    made.generateMipmaps = true;
    made.anisotropy = 8;
    made.repeat.set(1, -1);
    made.offset.set(0, 1);
    made.needsUpdate = true;
    return made;
  }, [picture]);
  useEffect(() => () => texture.dispose(), [texture]);
  return texture;
}

/**
 * The clearance map laid on the model's floor: the same picture and red edge the plan draws, and a ring with its
 * width at each gap the route cannot get through. It never takes the pointer, so dragging works through it.
 */
export function ClearanceFloor({ overlay, floorZ }: { overlay: ClearanceOverlay; floorZ: number }) {
  const { field, tightEdge } = overlay.picture;
  const texture = useFloorTexture(overlay.picture);
  const centre = roomPointOf(field, field.columns / 2, field.rows / 2);
  const opacity = overlay.stale ? STALE_OPACITY : 1;
  const [tight, halo] = useMemo(() => [tokenValue(TIGHT_TOKEN), tokenValue(HALO_TOKEN)], []);
  const edge = useMemo(
    () => tightEdge.flatMap(([a, b]) => [[a.x, floorZ + LIFT.edge, -a.y], [b.x, floorZ + LIFT.edge, -b.y]] as [number, number, number][]),
    [tightEdge, floorZ],
  );
  return (
    <group>
      <mesh position={[centre.x, floorZ + LIFT.field, -centre.y]} rotation={[-Math.PI / 2, 0, (field.rotationDegrees * Math.PI) / 180]} renderOrder={1} raycast={NEVER_HIT}>
        <planeGeometry args={[field.columns * field.cellMeters, field.rows * field.cellMeters]} />
        <meshBasicMaterial map={texture} transparent opacity={opacity} depthWrite={false} toneMapped={false} />
      </mesh>
      {edge.length > 0 && <Line points={edge} segments color={halo} lineWidth={3.5} transparent opacity={opacity} depthWrite={false} renderOrder={2} raycast={NEVER_HIT} />}
      {edge.length > 0 && <Line points={edge} segments color={tight} lineWidth={1.25} transparent opacity={opacity} depthWrite={false} renderOrder={3} raycast={NEVER_HIT} />}
      {pinchesToMark(field).map((pinch) => (
        <group key={pinch.finding_id} position={[pinch.point.x, floorZ + LIFT.ring, -pinch.point.y]}>
          <mesh rotation-x={-Math.PI / 2} renderOrder={4} raycast={NEVER_HIT}>
            <ringGeometry args={[RING_METERS.inner, RING_METERS.outer, 40]} />
            <meshBasicMaterial color={tight} side={DoubleSide} transparent opacity={opacity} depthWrite={false} toneMapped={false} />
          </mesh>
          <Html zIndexRange={[20, 0]} style={{ pointerEvents: "none", opacity }}>
            <span className="flex -translate-x-1/2 -translate-y-full flex-col items-center pb-4">
              <span className="measurement whitespace-nowrap rounded-md bg-sheet px-2 py-1 text-sm font-semibold text-clearance-tight shadow-md">{pinchWords(pinch, field.bands)}</span>
            </span>
          </Html>
        </group>
      ))}
    </group>
  );
}

/** The map never takes the pointer, so a drag or a tap reaches the piece or floor beneath it. */
const NEVER_HIT = () => {};
