"use client";

import { useEffect, useState } from "react";

const CURSOR_IDLE_MS = 1400;

function toggleFullscreen() {
  if (document.fullscreenElement) {
    void document.exitFullscreen();
    return;
  }
  void document.documentElement.requestFullscreen({ navigationUI: "hide" });
}

export function useFullscreenShortcut() {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "f" || event.metaKey || event.ctrlKey) return;
      event.preventDefault();
      toggleFullscreen();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);
}

export function useIdleCursor() {
  const [isIdle, setIsIdle] = useState(false);

  useEffect(() => {
    let timer = window.setTimeout(() => setIsIdle(true), CURSOR_IDLE_MS);

    function wake() {
      setIsIdle(false);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setIsIdle(true), CURSOR_IDLE_MS);
    }

    window.addEventListener("pointermove", wake);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointermove", wake);
    };
  }, []);

  return isIdle;
}
