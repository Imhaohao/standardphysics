"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { proposeFix, saveOwnerWishes, turnDownPlacements } from "@/lib/layout-client";
import type { OwnerWish, ProposalResult, TurnDownRequest } from "@/types/contracts";

/** One finding's proposal and the owner's saved wishes: ask for a layout, and keep things before asking again. */
export function useProposalReview(scanId: string, revision: number, saved: OwnerWish[]) {
  const router = useRouter();
  const [wishes, setWishes] = useState(saved);
  const [result, setResult] = useState<ProposalResult | null>(null);
  const [state, setState] = useState<"idle" | "looking" | "failed">("idle");

  async function run(work: () => Promise<void>) {
    if (state === "looking") return;
    setState("looking");
    try {
      await work();
      setState("idle");
    } catch {
      setState("failed");
    }
  }

  async function ask(findingId: string): Promise<ProposalResult> {
    const next = await proposeFix(scanId, revision, [findingId]);
    setResult(next);
    return next;
  }

  const propose = (findingId: string, then?: (result: ProposalResult) => void) =>
    run(async () => {
      const found = await ask(findingId);
      then?.(found);
    });

  const keep = (next: OwnerWish[], findingId: string | null, then?: (result: ProposalResult) => void) =>
    run(async () => {
      setWishes((await saveOwnerWishes(scanId, next)).owner_wishes);
      router.refresh();
      if (!findingId) return;
      const found = await ask(findingId);
      then?.(found);
    });

  /** Saves each turned-down piece as a spot to keep it out of, then hands over, so the plan can put it back. */
  const turnDown = (request: TurnDownRequest, then: () => void) =>
    run(async () => {
      setWishes((await turnDownPlacements(scanId, request)).owner_wishes);
      router.refresh();
      then();
    });

  return { wishes, result, looking: state === "looking", failed: state === "failed", propose, keep, turnDown, clear: () => setResult(null) };
}

export type ProposalReviewState = ReturnType<typeof useProposalReview>;
