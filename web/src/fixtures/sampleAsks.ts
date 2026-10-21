import type { AnswerInput, AnswerValue, Report } from "@/lib/api/types";
import type { Ask, Finding, FindingStatus } from "@/lib/findings/types";

/**
 * The sample report was captured before sp-core attached asks to findings, so the fixture adds them here, for the
 * metrics its needs_info messages name. Answering one settles it with a simple stand-in for sp-core's evaluation:
 * enough to show the flow in fixture mode, never a claim about a real shop.
 */
interface SampleAsk {
  ask: Omit<Ask, "metric" | "subject_id">;
  settle: (value: AnswerValue) => FindingStatus;
}

/** Applies when yes: the rule then wants a tape measure, which the scan could not take. */
const STILL_MEASURE = "needs_info";

function yesNo(prompt: string, outcome: { yes: FindingStatus; no: FindingStatus }, photo = false): SampleAsk {
  return { ask: { prompt, value_type: "boolean", unit: "", options: [], photo }, settle: (value) => (value === true ? outcome.yes : outcome.no) };
}

function inches(prompt: string, meets: (value: number) => boolean): SampleAsk {
  return { ask: { prompt, value_type: "number", unit: "in", options: [], photo: true }, settle: (value) => (typeof value === "number" && meets(value) ? "pass" : "fail") };
}

const SAMPLE_ASKS: Record<string, SampleAsk> = {
  "door.projection_below_34": inches("How far does anything on the door stick into the doorway below 34 inches up? Enter 0 if nothing does.", (value) => value === 0),
  "door.projection_34_80": inches("How far does the furthest thing on the door, like a closer arm, stick into the doorway between 34 and 80 inches up?", (value) => value <= 4),
  "door.bottom_smooth_surface_height": inches("How tall is the smooth surface along the bottom of the door on the push side?", (value) => value >= 10),
  "door.is_revolving_or_turnstile": yesNo("Is this a revolving door or a turnstile?", { yes: "fail", no: "pass" }, true),
  "door.hardware_requires_tight_grasp": yesNo("Does the handle need tight grasping, pinching or twisting to open, like a round knob does?", { yes: "fail", no: "pass" }, true),
  "door.has_latch": yesNo("Does this door have a latch?", { yes: STILL_MEASURE, no: "not_applicable" }, true),
  "door.is_fire_door": yesNo("Is this a rated fire door?", { yes: "not_applicable", no: STILL_MEASURE }),
  "toilet_room.signage_geometric_symbol": yesNo("Does the restroom door carry California's geometric symbol, a circle, a triangle, or both?", { yes: STILL_MEASURE, no: "not_applicable" }, true),
  "floor.surface_firm_stable_slip_resistant": yesNo("Is the floor firm, stable and slip resistant? Deep carpet, loose mats and gravel aren't.", { yes: "pass", no: "fail" }, true),
  "site.has_fire_alarm_system": yesNo("Does the building have a fire alarm system?", { yes: STILL_MEASURE, no: "not_applicable" }),
  "site.barrier_removal_plan": yesNo("Do you keep a plan for removing access barriers where it's readily achievable, and work through it?", { yes: "pass", no: "fail" }),
  "site.has_written_maintenance_practice": yesNo("Do staff keep aisles, counters and restroom clearances free of stock, chairs and other movable things?", { yes: "pass", no: "fail" }),
  "site.altered_since_2012": yesNo("Has the space been remodeled or altered since March 15, 2012?", { yes: STILL_MEASURE, no: "not_applicable" }),
  "site.employee_only_areas_excluded": yesNo("Are the rooms you left out of the scan used only by staff?", { yes: "pass", no: "fail" }),
  "site.has_customer_parking": yesNo("Do you provide on-site parking for customers?", { yes: STILL_MEASURE, no: "not_applicable" }),
  "site.tactile_exit_signs_complete": yesNo("Does every exit door that needs a tactile exit sign have one?", { yes: "pass", no: "fail" }, true),
  "site.isa_signage_at_inaccessible_entrances": yesNo("Do the entrances that aren't accessible have signs pointing to the one that is?", { yes: "pass", no: "fail" }, true),
};

const METRIC_IN_MESSAGE = /\(([a-z_]+(?:\.[a-z0-9_]+)+)\)\)\.?$/;

export const answerKey = (subjectId: string, metric: string) => JSON.stringify([subjectId, metric]);

function sampleAskFor(finding: Finding) {
  if (finding.status !== "needs_info") return null;
  const metric = METRIC_IN_MESSAGE.exec(finding.message)?.[1];
  const sample = metric ? SAMPLE_ASKS[metric] : undefined;
  return sample && metric ? { metric, sample } : null;
}

function settled(finding: Finding, status: FindingStatus): Finding {
  const message = status === "needs_info" ? `${finding.title}: needs more information (needs a photo or tape measurement; the scan box does not resolve this detail).` : `${finding.title}: settled by your answer.`;
  return { ...finding, status, message, ask: null };
}

function withSampleAsk(finding: Finding, answers: ReadonlyMap<string, AnswerInput>): Finding {
  const found = sampleAskFor(finding);
  if (!found) return finding;
  const answer = answers.get(answerKey(finding.subject_id, found.metric));
  if (answer) return settled(finding, found.sample.settle(answer.value));
  return { ...finding, ask: { ...found.sample.ask, metric: found.metric, subject_id: finding.subject_id } };
}

/** The sample report with asks on its open questions, re-evaluated against the answers given so far. */
export function sampleReportWithAnswers(report: Report, answers: ReadonlyMap<string, AnswerInput>): Report {
  return { ...report, findings: report.findings.map((finding) => withSampleAsk(finding, answers)) };
}
