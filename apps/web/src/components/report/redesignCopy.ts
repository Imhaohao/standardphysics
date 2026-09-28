import { formatInches } from "@/lib/findings";
import type { Finding } from "@/types/contracts";
import type { ClauseRow, ScheduledMove } from "./redesign";

const SPOT_WORDS = ["no spots", "one spot", "two spots", "three spots", "four spots", "five spots"];

function spots(count: number): string {
  return SPOT_WORDS[count] ?? `${count} spots`;
}

export interface RedesignTally {
  failing: number;
  cleared: number;
  broken: number;
}

export function tally(rows: ClauseRow[]): RedesignTally {
  return {
    failing: rows.filter((row) => row.change !== "new_problem").length,
    cleared: rows.filter((row) => row.change === "cleared").length,
    broken: rows.filter((row) => row.change === "new_problem").length,
  };
}

function withoutPlan({ failing }: RedesignTally): string {
  if (failing === 0) return "Nothing the scan measured fails the 2010 ADA Standards.";
  return `${capitalize(spots(failing))} ${failing === 1 ? "fails" : "fail"} the 2010 ADA Standards.`;
}

function clearedPart({ failing, cleared }: RedesignTally, planName: string): string {
  const all: Record<number, string> = { 1: "it", 2: "both" };
  if (cleared === failing) return `${planName} clears ${all[failing] ?? `all ${failing}`}`;
  return `${planName} clears ${cleared} of them`;
}

function withPlan(count: RedesignTally, planName: string): string {
  const broken = count.broken > 0 ? `, and ${spots(count.broken)} that ${count.broken === 1 ? "passes" : "pass"} today would fail` : "";
  if (count.failing === 0 && count.broken === 0) return `Nothing the scan measured fails, as scanned or in ${planName}.`;
  if (count.failing === 0) return `Nothing the scan measured fails today, but in ${planName} ${spots(count.broken)} would.`;
  return `${withoutPlan(count)} ${clearedPart(count, planName)}${broken}.`;
}

/** The report's one-line answer: what fails, and what the plan does about it. */
export function verdict(rows: ClauseRow[], planName: string | null): string {
  const count = tally(rows);
  return planName ? withPlan(count, planName) : withoutPlan(count);
}

export function constructionSentence(schedule: ScheduledMove[]): string {
  const builtIn = schedule.filter((move) => move.builtIn).map((move) => move.node.label.toLowerCase());
  if (builtIn.length === 0) return "Every piece it moves stands free, so it needs no construction.";
  return `It relocates the ${builtIn.join(" and the ")}, which is built in, so it needs construction.`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** What was measured against what the section sets, or null when the check measured nothing. */
export function measuredAgainst(finding: Finding): string | null {
  if (finding.measured_inches === null || finding.required_inches === null) return null;
  return `Measured ${formatInches(finding.measured_inches)} where ${finding.citation.section} sets ${formatInches(finding.required_inches)}.`;
}

const NUDGE_INCHES = 0.25;

function along(inches: number, positive: string, negative: string): string | null {
  if (Math.abs(inches) < NUDGE_INCHES) return null;
  return `${formatInches(Math.abs(inches))} ${inches > 0 ? positive : negative}`;
}

/** A move in the drawing's own directions, since the plan beside it has no compass. */
export function describeMove(move: ScheduledMove): string {
  const turn = Math.round(Math.abs(move.turnDegrees));
  const parts = [
    along(move.inchesAcross, "right", "left"),
    along(move.inchesUp, "up", "down"),
    turn ? `turned ${turn}°` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : "Stays put";
}

/** How the plan answers one failing spot, in the owner's words. */
export function remedy(row: ClauseRow, schedule: ScheduledMove[], planName: string | null): string | null {
  const movers = schedule.filter((move) => move.serves.includes(row)).map((move) => move.node.label.toLowerCase());
  if (row.change === "cleared") {
    return movers.length > 0 ? `${planName} moves the ${[...new Set(movers)].join(" and the ")}, which clears it.` : `${planName} clears it.`;
  }
  if (row.change === "new_problem") return `${planName} makes this fail.`;
  return row.before?.fix ?? null;
}
