"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";
import { AmbientInk } from "@/lib/ink/ambientInk";

const INK_LAYER_CLASS = "pointer-events-none absolute inset-0 -z-10 size-full print:hidden";

/** The paper every page is printed on: ambient ink drafted into its empty space, under a layer of grain. */
export function PaperInk({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const pageRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const paintRef = useRef<HTMLCanvasElement>(null);
  const liveRef = useRef<HTMLCanvasElement>(null);
  const inkRef = useRef<AmbientInk | null>(null);

  useEffect(() => {
    const [page, content, paint, live] = [pageRef.current, contentRef.current, paintRef.current, liveRef.current];
    if (!page || !content || !paint || !live) return;
    const ink = new AmbientInk({ page, content, paint, live });
    inkRef.current = ink;
    return () => {
      ink.dispose();
      inkRef.current = null;
    };
  }, []);

  useEffect(() => {
    inkRef.current?.pageChanged();
  }, [pathname]);

  return (
    <div ref={pageRef} className="relative isolate min-h-dvh">
      <canvas ref={paintRef} data-ink-layer aria-hidden className={INK_LAYER_CLASS} />
      <canvas ref={liveRef} data-ink-layer aria-hidden className={INK_LAYER_CLASS} />
      <div ref={contentRef}>{children}</div>
      <div aria-hidden className="paper-grain pointer-events-none fixed inset-0 z-50 opacity-10 print:hidden" />
    </div>
  );
}
