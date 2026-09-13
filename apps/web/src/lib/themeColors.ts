import { Color } from "three";

const themeColorTokens = {
  ink: "--color-ink",
  clay: "--color-clay",
  floor: "--color-clay-floor",
  glass: "--color-clay-glass",
  tape: "--color-tape",
  tapeDeep: "--color-tape-deep",
  fail: "--color-fail",
  pass: "--color-pass",
} as const;

export type ThemeColorName = keyof typeof themeColorTokens;
export type ThemeColors = Record<ThemeColorName, Color>;

export function readThemeColors(): ThemeColors {
  const styles = getComputedStyle(document.documentElement);
  const entries = Object.entries(themeColorTokens).map(([name, token]) => [
    name,
    new Color(styles.getPropertyValue(token).trim()),
  ]);
  return Object.fromEntries(entries) as ThemeColors;
}

export function cssColor(name: ThemeColorName) {
  return `var(${themeColorTokens[name]})`;
}
