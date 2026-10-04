"use client";

import { useCallback, useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function readSwitch(key: string, fallback: boolean): boolean {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "on";
  } catch {
    // A private window refuses storage, and then the choice is the default every time.
    return fallback;
  }
}

export function writeSwitch(key: string, on: boolean): void {
  try {
    window.localStorage.setItem(key, on ? "on" : "off");
  } catch {
    // Nothing to remember it with, and nothing this page can do about that.
  }
}

/**
 * An on or off choice this browser remembers, such as whether to show the team's tools.
 *
 * The server renders `fallback`, so the first paint is always the default one and a remembered choice appears only
 * once the browser reports it. Kept per browser rather than per account: it describes who is looking, not who owns
 * the shop. The storage event carries a change to every open tab.
 */
export function useStoredSwitch(key: string, fallback = false): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(subscribe, () => readSwitch(key, fallback), () => fallback);

  const choose = useCallback((next: boolean) => {
    writeSwitch(key, next);
    listeners.forEach((listener) => listener());
  }, [key]);

  return [on, choose];
}
