"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

const EVERY_MS = 2000;

/** Re-reads the page from the server while something it shows is still being worked on. */
export function RefreshWhile({ pending }: { pending: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => router.refresh(), EVERY_MS);
    return () => clearInterval(timer);
  }, [pending, router]);
  return null;
}
