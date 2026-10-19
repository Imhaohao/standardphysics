/** The Finding contract (REBUILD.md; server/src/findings.rs). Measurements arrive in the units rules/metrics.json uses. */
export type FindingStatus = "pass" | "fail" | "needs_info" | "not_applicable";
export type Jurisdiction = "ADA2010" | "CBC11B";

export interface Measured {
  value: number;
  unit: string;
}

/** A rule's test, as the rulepack writes it: `{ op, value | [lo, hi], unit }`. Anything else is shown as text. */
export interface MeasureRequirement {
  op: "<=" | ">=" | "<" | ">" | "between" | "==";
  value: number | [number, number];
  unit: string;
}

export interface Finding {
  rule_id: string;
  jurisdiction: Jurisdiction | (string & {});
  section: string;
  subject_id: string;
  status: FindingStatus;
  measured: Measured | null;
  required: MeasureRequirement | string | Record<string, unknown> | null;
  message: string;
  evidence: unknown;
}

export interface StatusCounts {
  pass: number;
  fail: number;
  needs_info: number;
  not_applicable: number;
}

export interface FindingsSummary {
  total: StatusCounts;
  by_jurisdiction: Record<string, StatusCounts>;
}
