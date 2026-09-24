"use client";

import { useCallback, useSyncExternalStore } from "react";

const KEY = "sp_developer_mode";
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function stored(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "on";
  } catch {
    // A private window refuses storage. The owner's view is the safe answer.
    return false;
  }
}

/**
 * Whether to show the tools this team built for itself.
 *
 * The server renders the shop owner's view, which is what the third argument
 * says, so the first paint is always the plain one and the extra panels appear
 * only once the browser reports that this person asked for them. Kept per
 * browser rather than per account: it describes who is looking, not who owns
 * the shop. The storage event carries a change to every open tab.
 */
export function useDeveloperMode(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(subscribe, stored, () => false);

  const choose = useCallback((next: boolean) => {
    try {
      window.localStorage.setItem(KEY, next ? "on" : "off");
    } catch {
      // Nothing to remember it with, and nothing this page can do about that.
    }
    listeners.forEach((listener) => listener());
  }, []);

  return [on, choose];
}
