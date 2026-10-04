"use client";

import { useSyncExternalStore } from "react";

/** Tailwind's `lg`, where panels sit over the model instead of under it. */
const WIDE_SCREEN = "(min-width: 64rem)";

function subscribeToWidth(onChange: () => void) {
  const query = window.matchMedia(WIDE_SCREEN);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function useWideScreen(): boolean {
  return useSyncExternalStore(subscribeToWidth, () => window.matchMedia(WIDE_SCREEN).matches, () => false);
}
