import type { Assessment, Scan } from "@/types/contracts";
import { countNeedingAttention } from "./findings";

const STATE_LABEL: Record<Scan["state"], string> = {
  uploading: "Uploading",
  measuring: "Measuring your shop",
  checking: "Checking",
  ready: "Ready",
  failed: "This scan didn't go through. Scan the shop again.",
};

export function scanStatus(scan: Scan, assessment: Assessment | null): string {
  if (scan.state !== "ready" || assessment === null) return STATE_LABEL[scan.state];
  if (assessment.rules_checked === 0) return "Checks start once a person reviews the rules";
  const attention = countNeedingAttention(assessment.findings);
  if (attention === 0) return "Everything we checked passes";
  return attention === 1 ? "1 thing to look at" : `${attention} things to look at`;
}
