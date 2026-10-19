export type RandomSource = () => number;

export function seededSource(seed: number): RandomSource {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class Random {
  constructor(private readonly source: RandomSource = Math.random) {}

  next() {
    return this.source();
  }

  float(min = 0, max = 1) {
    return min + this.source() * (max - min);
  }

  int(min: number, maxExclusive: number) {
    return Math.floor(this.float(min, maxExclusive));
  }

  chance(probability: number) {
    return this.source() < probability;
  }

  sign() {
    return this.chance(0.5) ? -1 : 1;
  }

  pick<T>(items: readonly T[]): T {
    const item = items[this.int(0, items.length)];
    if (item === undefined) throw new Error("Cannot pick from an empty list.");
    return item;
  }

  weighted<T>(weights: readonly (readonly [T, number])[]): T {
    const total = weights.reduce((sum, [, weight]) => sum + weight, 0);
    let roll = this.float(0, total);
    for (const [item, weight] of weights) {
      roll -= weight;
      if (roll < 0) return item;
    }
    return weights[weights.length - 1]![0];
  }

  shuffled<T>(items: readonly T[]): T[] {
    const result = [...items];
    for (let i = result.length - 1; i > 0; i--) {
      const j = this.int(0, i + 1);
      [result[i], result[j]] = [result[j]!, result[i]!];
    }
    return result;
  }
}

function hash(index: number) {
  const value = Math.sin(index * 127.1 + 311.7) * 43758.5453;
  return value - Math.floor(value);
}

/** Value noise in [0, 1] that varies smoothly along x; the brush uses it so ink texture stays stable frame to frame. */
export function smoothNoise(x: number) {
  const index = Math.floor(x);
  const fraction = x - index;
  const eased = fraction * fraction * (3 - 2 * fraction);
  return hash(index) + (hash(index + 1) - hash(index)) * eased;
}
