import { room } from "@/lib/fixtureShop";

const SWEEP_OVERSHOOT = 0.6;

export const sweepStartZ = room.depth / 2 + SWEEP_OVERSHOOT;
export const sweepEndZ = -(room.depth / 2 + SWEEP_OVERSHOOT);

export function sweepFrontZ(progress: number) {
  return sweepStartZ + (sweepEndZ - sweepStartZ) * progress;
}

export function sweepProgressAt(z: number) {
  return (sweepStartZ - z) / (sweepStartZ - sweepEndZ);
}
