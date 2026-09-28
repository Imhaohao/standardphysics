import { facts } from "@/lib/facts";
import type { Assessment, Scan } from "@/types/contracts";

const MS_PER_MINUTE = 60_000;

/**
 * Minutes from the scan arriving to its first checked results. The first time
 * is kept apart from the assessment's own stamp, which moves with every re-check.
 */
export function minutesToResults(scan: Scan): number | null {
  if (!scan.results_ready_at) return null;
  const minutes = (Date.parse(scan.results_ready_at) - Date.parse(scan.created_at)) / MS_PER_MINUTE;
  return Number.isFinite(minutes) && minutes >= 0 ? minutes : null;
}

export function formatMinutes(minutes: number): string {
  if (minutes < 1) return "Under a minute";
  const whole = Math.round(minutes);
  if (whole < 60) return whole === 1 ? "1 minute" : `${whole} minutes`;
  const [hours, rest] = [Math.floor(whole / 60), whole % 60];
  const hourText = hours === 1 ? "1 hour" : `${hours} hours`;
  return rest === 0 ? hourText : `${hourText} ${rest} min`;
}

/** Every number the scan measured, which a person would otherwise take with a tape. */
export function measurementsTaken(assessment: Assessment | null): number {
  return (assessment?.findings ?? []).filter((finding) => finding.measured_inches !== null).length;
}

/** Business days from booking an inspection's site visit to holding its report, from the published turnaround. */
export function inspectionBusinessDays(): { fewest: number; most: number } {
  const { onSiteDays, reportBusinessDays } = facts.inspectionTurnaround;
  return { fewest: onSiteDays + reportBusinessDays.fewest, most: onSiteDays + reportBusinessDays.most };
}
