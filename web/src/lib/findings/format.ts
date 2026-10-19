import type { Finding, FindingStatus, Measured } from "./types";

const UNIT_SUFFIX: Record<string, string> = { in: '"', ft: "'", lbf: " lbf", s: " s", deg: "°", "%": "%", count: "", ratio: "", "": "" };

function trimmed(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
}

export function formatQuantity(value: number, unit: string) {
  if (unit === "ratio" && value > 0 && value < 1) return `1:${Math.round(1 / value)}`;
  return `${trimmed(value)}${UNIT_SUFFIX[unit] ?? ` ${unit}`}`;
}

function isRange(measured: Measured) {
  return measured.lo != null && measured.hi != null && Math.abs(measured.hi - measured.lo) >= 0.05;
}

/** 32.9", 33.5" to 34.5" for a range the scan could not pin down, or the engine's own words ("yes"). */
export function formatMeasured(measured: Measured | null | undefined) {
  if (!measured) return null;
  if (isRange(measured)) return `${formatQuantity(measured.lo!, measured.unit)} to ${formatQuantity(measured.hi!, measured.unit)}`;
  if (measured.value != null) return formatQuantity(measured.value, measured.unit);
  return measured.text || null;
}

const NUMBER = String.raw`(-?\d+(?:\.\d+)?)`;
const COMPARISON = new RegExp(String.raw`^(>=|<=|>|<|==)\s*${NUMBER}\s*(\S*)$`);
const BETWEEN = new RegExp(String.raw`^between\s+${NUMBER}\s+and\s+${NUMBER}\s*(\S*)$`);

const OPERATOR_WORDS: Record<string, (value: string) => string> = {
  ">=": (value) => `${value} min`,
  ">": (value) => `more than ${value}`,
  "<=": (value) => `${value} max`,
  "<": (value) => `under ${value}`,
  "==": (value) => `exactly ${value}`,
};

function formatClause(clause: string) {
  const between = BETWEEN.exec(clause);
  if (between) return `${formatQuantity(Number(between[1]), between[3]!)} to ${formatQuantity(Number(between[2]), between[3]!)}`;
  const comparison = COMPARISON.exec(clause);
  if (comparison) return OPERATOR_WORDS[comparison[1]!]!(formatQuantity(Number(comparison[2]), comparison[3]!));
  return clause;
}

/** sp-core writes requirements as ">= 36 in" or "between 28 and 34 in", joined with "and" / "or"; this reads them as 36" min. */
export function formatRequirement(required: string | null | undefined): string | null {
  const text = required?.trim();
  if (!text) return null;
  return text
    .split(/\s+(and|or)\s+(?=[<>=]|between\b)/)
    .map((part) => (part === "and" || part === "or" ? part : formatClause(part)))
    .join(" ");
}

/** What sp-core says it is missing, read from a needs_info message: "Title: needs more information (reason)." */
export function missingReason(finding: Pick<Finding, "message">) {
  const match = /needs more information \((.*)\)\.?$/.exec(finding.message);
  return match ? match[1]! : null;
}

const OWNER_ASKS: [RegExp, string][] = [
  [/straddles the limit/, "It's too close to the limit to call from the scan. A tape measure settles it."],
  [/photo or tape measurement/, "Measure it, or send us a photo."],
  [/exterior arrival route/, "Send us a photo of the way in from the street."],
  [/photo of the element/, "Send us a photo of it."],
  [/answer from the owner/, "Tell us about it."],
  [/floor mesh height field/, "The scan can't measure floor slope yet, so check that the floor here is level."],
  [/no route reaches this door/, "We couldn't find a route to this door. Tell us whether customers use it."],
  [/far side was not scanned/, "Tell us whether the other side of this opening is outside."],
  [/swing not captured/, "Tell us which way the door swings."],
];

/** The one thing the owner can do to settle a needs_info finding, in plain words. */
export function ownerAsk(finding: Pick<Finding, "message">) {
  const reason = missingReason(finding) ?? finding.message;
  const ask = OWNER_ASKS.find(([pattern]) => pattern.test(reason));
  if (ask) return ask[1];
  return reason.charAt(0).toUpperCase() + reason.slice(1);
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
