import type { Random } from "./random";

/** One drafting grid unit stands for six inches, so a 12 px unit draws the sheet at 1" = 4'-0" on screen. */
export const INCHES_PER_UNIT = 6;
export const SHEET_SCALE_LABEL = `1" = 4'-0"`;

const REQUIREMENTS = ['36" min', '32" min', '48" max', '36" max', '80" min', '30" × 48"', "1:12 max", '18" min'];

const CODE_SECTIONS = ["§403.5.1", "§404.2.3", "§304.3", "§305.3", "§308.2.1", "§405.2", "§904.4.1", "§307.4", "§404.2.4.1"];

export function inchesForLength(lengthPx: number, unit: number) {
  return `${Math.round((lengthPx / unit) * INCHES_PER_UNIT)}"`;
}

export function requirementNote(rng: Random) {
  return rng.pick(REQUIREMENTS);
}

export function codeSection(rng: Random) {
  return rng.pick(CODE_SECTIONS);
}

export function detailNumber(rng: Random) {
  return String(rng.int(1, 13));
}

export function sheetReference(rng: Random) {
  return `A${rng.int(1, 5)}.${rng.int(1, 5)}`;
}
