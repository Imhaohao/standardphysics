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

/** The figure a measurement is shown as: whole within a twentieth of a whole inch, otherwise to a tenth. */
export function shownFigure(inches: number): string {
  const rounded = Math.round(inches);
  return Math.abs(inches - rounded) < 0.05 ? `${rounded}` : inches.toFixed(1);
}

export function formatInches(inches: number): string {
  return `${shownFigure(inches)} in`;
}

export function countNeedingAttention(findings: Finding[]): number {
  return findings.filter((finding) => finding.outcome !== "passes").length;
}

/** What the viewer frames and highlights: a finding, or the subject of a question. */
export type Focus = Pick<Finding, "locus" | "outcome" | "required_inches">;

export function focusOnLocus(locus: Locus): Focus {
  return { locus, outcome: "question", required_inches: null };
}
