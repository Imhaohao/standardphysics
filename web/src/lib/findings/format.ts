import type { Finding, FindingStatus, Measured, MeasureRequirement } from "./types";

const OPERATOR_WORDS: Record<Exclude<MeasureRequirement["op"], "between">, (value: string) => string> = {
  ">=": (value) => `${value} min`,
  ">": (value) => `more than ${value}`,
  "<=": (value) => `${value} max`,
  "<": (value) => `under ${value}`,
  "==": (value) => `exactly ${value}`,
};

const UNIT_SUFFIX: Record<string, string> = { in: '"', ft: "'", lbf: " lbf", s: " s", ratio: "" };

export function formatQuantity(value: number, unit: string) {
  if (unit === "ratio") return value > 0 ? `1:${Math.round(1 / value)}` : "0";
  const rounded = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
  return `${rounded}${UNIT_SUFFIX[unit] ?? ` ${unit}`}`;
}

export function formatMeasured(measured: Measured | null) {
  return measured ? formatQuantity(measured.value, measured.unit) : null;
}

function isMeasureRequirement(required: unknown): required is MeasureRequirement {
  return typeof required === "object" && required !== null && "op" in required && "value" in required && "unit" in required;
}

export function formatRequirement(required: Finding["required"]): string | null {
  if (typeof required === "string") return required;
  return isMeasureRequirement(required) ? formatMeasureRequirement(required) : null;
}

function formatMeasureRequirement({ op, value, unit }: MeasureRequirement): string | null {
  if (op === "between" && Array.isArray(value)) return `${formatQuantity(value[0], unit)} to ${formatQuantity(value[1], unit)}`;
  if (Array.isArray(value) || op === "between") return null;
  return OPERATOR_WORDS[op](formatQuantity(value, unit));
}

const JURISDICTION_NAMES: Record<string, string> = { ADA2010: "2010 ADA Standards", CBC11B: "California Building Code 11B" };

export function jurisdictionName(jurisdiction: string) {
  return JURISDICTION_NAMES[jurisdiction] ?? jurisdiction;
}

/** "§403.5.1" for the ADA, "§11B-403.5.1" for California, whichever way the rulepack spelled the section. */
export function citation(finding: Pick<Finding, "jurisdiction" | "section">) {
  const bare = finding.section.replace(/^§\s*/, "").replace(/^11B-/i, "");
  if (!bare) return null;
  return finding.jurisdiction === "CBC11B" ? `§11B-${bare}` : `§${bare}`;
}

export const STATUS_LABEL: Record<FindingStatus, string> = {
  fail: "Needs fixing",
  needs_info: "We need to ask you",
  pass: "Meets the rule",
  not_applicable: "Doesn't apply",
};
