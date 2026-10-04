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

function wholeOrTenth(inches: number): string {
  const rounded = Math.round(inches);
  return Math.abs(inches - rounded) < 0.05 ? `${rounded}` : inches.toFixed(1);
}

function readsDifferently(inches: number, required: number): boolean {
  return wholeOrTenth(inches) !== wholeOrTenth(required) || Math.abs(inches - required) < 1e-6;
}

function separatingDigits(inches: number, required: number): string {
  for (const places of [1, 2, 3]) {
    const digits = inches.toFixed(places);
    if (digits !== required.toFixed(places)) return digits;
  }
  return inches.toFixed(3);
}

/**
 * Prints whole inches when a value is within 0.05 of one, and one decimal place otherwise.
 *
 * When it is given the number a check holds the measurement to, a value that
 * would round to read the same as that number without equalling it keeps the
 * digits that separate the two. Otherwise a failing 35.98 in would read
 * "36 in" beside a 36 in requirement. `measured` in the agents package's
 * numbers.py applies the same rule to the findings' text.
 */
export function formatInches(inches: number, required?: number | null): string {
  if (required == null || readsDifferently(inches, required)) return `${wholeOrTenth(inches)} in`;
  return `${separatingDigits(inches, required)} in`;
}

export function countNeedingAttention(findings: Finding[]): number {
  return findings.filter((finding) => finding.outcome !== "passes").length;
}

/** What the viewer frames and highlights: a finding, or the subject of a question. */
export type Focus = Pick<Finding, "locus" | "outcome" | "required_inches">;

export function focusOnLocus(locus: Locus): Focus {
  return { locus, outcome: "question", required_inches: null };
}
