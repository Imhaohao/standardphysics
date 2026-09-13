import type { Finding, Locus } from "@/types/contracts";

export type FindingGroups = { problems: Finding[]; questions: Finding[]; passes: Finding[] };

export function groupFindings(findings: Finding[]): FindingGroups {
  return {
    problems: findings.filter((finding) => finding.outcome === "problem"),
    questions: findings.filter((finding) => finding.outcome === "question"),
    passes: findings.filter((finding) => finding.outcome === "passes"),
  };
}

export function findingForNode(findings: Finding[], nodeId: string): Finding | undefined {
  const order = [...groupFindings(findings).problems, ...findings];
  return order.find((finding) => finding.locus?.node_ids.includes(nodeId));
}

export function formatInches(inches: number): string {
  const rounded = Math.round(inches);
  return Math.abs(inches - rounded) < 0.05 ? `${rounded} in` : `${inches.toFixed(1)} in`;
}

export function countNeedingAttention(findings: Finding[]): number {
  return findings.filter((finding) => finding.outcome !== "passes").length;
}

/** What the viewer frames and highlights: a finding, or the subject of a question. */
export type Focus = Pick<Finding, "locus" | "outcome" | "required_inches">;

export function focusOnLocus(locus: Locus): Focus {
  return { locus, outcome: "question", required_inches: null };
}
