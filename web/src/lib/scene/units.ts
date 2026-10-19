export const METRES_PER_INCH = 0.0254;

export function metresToInches(metres: number) {
  return metres / METRES_PER_INCH;
}

/** 4.58 m reads as 15'-0". */
export function formatFeetAndInches(metres: number) {
  const totalInches = Math.round(metresToInches(metres));
  const feet = Math.floor(totalInches / 12);
  return `${feet}'-${totalInches - feet * 12}"`;
}
