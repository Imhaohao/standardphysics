import coverageJson from "../../../rules/coverage.json";
import { jurisdictionName } from "@/lib/findings/format";

/** One section of a code and whether the rulepack tests it, from rules/coverage.json. */
export interface CoverageEntry {
  jurisdiction: string;
  section: string;
  title: string;
  status: "covered" | "not_applicable_to_scope" | "deferred";
  rule_ids: string[];
  reason: string;
}

export interface DeferredSection {
  citation: string;
  title: string;
  reason: string;
}

export interface JurisdictionCoverage {
  jurisdiction: string;
  name: string;
  covered: number;
  notApplicable: number;
  deferred: DeferredSection[];
}

const CODE_SECTION = /^(11B-)?\d+(\.\d+)*$/;

/** "§404.2.3" or "§11B-404.2.3" for a building code section, and a regulation like "28 CFR 36.211" as written. */
export function coverageCitation(entry: Pick<CoverageEntry, "jurisdiction" | "section">) {
  return CODE_SECTION.test(entry.section) ? `§${entry.section}` : entry.section;
}

function summarize(jurisdiction: string, entries: CoverageEntry[]): JurisdictionCoverage {
  const count = (status: CoverageEntry["status"]) => entries.filter((entry) => entry.status === status).length;
  const deferred = entries
    .filter((entry) => entry.status === "deferred")
    .map((entry) => ({ citation: coverageCitation(entry), title: entry.title, reason: entry.reason }));
  return { jurisdiction, name: jurisdictionName(jurisdiction), covered: count("covered"), notApplicable: count("not_applicable_to_scope"), deferred };
}

/** Counts per jurisdiction, in the order the rulepack lists them, with every deferred section and why. */
export function coverageSummary(entries: readonly CoverageEntry[]): JurisdictionCoverage[] {
  const byJurisdiction = new Map<string, CoverageEntry[]>();
  for (const entry of entries) byJurisdiction.set(entry.jurisdiction, [...(byJurisdiction.get(entry.jurisdiction) ?? []), entry]);
  return [...byJurisdiction].map(([jurisdiction, list]) => summarize(jurisdiction, list));
}

/** The rulepack's coverage, read from rules/coverage.json when the site is built. */
export const RULEPACK_COVERAGE = coverageSummary((coverageJson as { entries: CoverageEntry[] }).entries);
