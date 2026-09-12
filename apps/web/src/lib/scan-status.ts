import type { Scan } from "@/types/contracts";

const STATE_LABEL: Record<Scan["state"], string> = {
  uploading: "Uploading",
  measuring: "Measuring your shop",
  checking: "Checking",
  ready: "Ready",
  failed: "This scan didn't go through. Scan the shop again.",
};

export function scanStatus(scan: Scan, attention: number | null): string {
  if (scan.state !== "ready") return STATE_LABEL[scan.state];
  if (attention === null) return "Ready";
  if (attention === 0) return "Everything we checked passes";
  return attention === 1 ? "1 thing to look at" : `${attention} things to look at`;
}
