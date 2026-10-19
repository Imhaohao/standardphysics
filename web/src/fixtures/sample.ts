import type { Report, Scan } from "@/lib/api/types";
import type { Finding, FindingStatus, Jurisdiction, MeasureRequirement } from "@/lib/findings/types";
import { countStatuses } from "@/lib/findings/group";
import type { Scene } from "@/lib/scene/types";
import sceneJson from "./sample-scene.json";

/**
 * The bundled sample shop. Its geometry is Apple's RoomPlan "living room" sample (fixtures/roomplan) run through
 * the converter. The findings are hand-written for the demo, but every measured value in them was taken from that
 * geometry: door and doorway widths, the gaps between pieces, shelf tops and counter heights.
 */
export const SAMPLE_SCAN_ID = "sample-living-room";
export const SAMPLE_SCENE = sceneJson as unknown as Scene;

export const SAMPLE_SCANS: Scan[] = [
  { id: SAMPLE_SCAN_ID, name: "Front of house", site_name: "Corner shop", status: "complete", created_at: "2026-10-14T17:20:00Z", updated_at: "2026-10-14T17:21:00Z" },
];

const ID_PREFIX = {
  door: "B435D27C",
  doorway: "E513B016",
  shelving: "C4B1116F",
  cabinetBack: "001CCADE",
  cabinetRight: "B66B176A",
  coffeeTable: "470F48AA",
  television: "77260FF4",
};

function elementId(prefix: string) {
  const elements = SAMPLE_SCENE.rooms.flatMap((room) => [...room.objects, ...room.openings]);
  const match = elements.find((element) => element.id.startsWith(prefix));
  if (!match) throw new Error(`The sample scene has no element ${prefix}.`);
  return match.id;
}

const SUBJECT = Object.fromEntries(Object.entries(ID_PREFIX).map(([key, prefix]) => [key, elementId(prefix)])) as Record<keyof typeof ID_PREFIX, string>;

type Code = "ada" | "cbc";
/** A value that differs between the two codes. */
type Split<T> = { ada: T; cbc: T };

interface PairSpec {
  subject: string;
  section: string;
  status: FindingStatus;
  measured?: number;
  required?: MeasureRequirement | Split<MeasureRequirement>;
  message: string;
  evidence: "measured" | "photo" | "owner";
}

const inches = (op: MeasureRequirement["op"], value: MeasureRequirement["value"]): MeasureRequirement => ({ op, value, unit: "in" });

function forCode<T extends object>(value: T | Split<T>, code: Code): T {
  return "ada" in value && "cbc" in value ? value[code] : (value as T);
}

const CODES: [Code, Jurisdiction, (section: string) => string][] = [
  ["ada", "ADA2010", (section) => section],
  ["cbc", "CBC11B", (section) => `11B-${section}`],
];

function bothCodes(spec: PairSpec): Finding[] {
  return CODES.map(([code, jurisdiction, section]) => ({
    rule_id: `${code}.${spec.section}`,
    jurisdiction,
    section: section(spec.section),
    subject_id: spec.subject,
    status: spec.status,
    measured: spec.measured === undefined ? null : { value: spec.measured, unit: "in" },
    required: spec.required ? forCode(spec.required, code) : null,
    message: spec.message,
    evidence: { kind: spec.evidence },
  }));
}

const SPECS: PairSpec[] = [
  {
    subject: SUBJECT.cabinetRight,
    section: "403.5.1",
    status: "fail",
    measured: 32.9,
    required: inches(">=", 36),
    message: "The aisle between this cabinet and the sofa is 32.9 inches wide. A wheelchair route needs 36 inches, so move the sofa about 3 inches toward the middle of the room.",
    evidence: "measured",
  },
  {
    subject: SUBJECT.shelving,
    section: "308.2.1",
    status: "fail",
    measured: 94.9,
    required: inches("<=", 48),
    message: "The top of this shelving is 94.9 inches up. Anything customers take for themselves has to sit at 48 inches or lower, so keep the upper shelves for stock.",
    evidence: "measured",
  },
  {
    subject: SUBJECT.cabinetBack,
    section: "904.4.1",
    status: "needs_info",
    measured: 37,
    required: { ada: inches("<=", 36), cbc: inches("<=", 34) },
    message: "Do you serve customers or take payment across this cabinet? If you do, part of it has to come down to counter height.",
    evidence: "owner",
  },
  {
    subject: SUBJECT.coffeeTable,
    section: "902.3",
    status: "needs_info",
    measured: 18.1,
    required: inches("between", [28, 34]),
    message: "Do customers sit at this table to eat or work? If they do, at least one table needs a top between 28 and 34 inches high.",
    evidence: "owner",
  },
  {
    subject: SUBJECT.door,
    section: "404.2.9",
    status: "needs_info",
    required: { op: "<=", value: 5, unit: "lbf" },
    message: "When you push the front door open, does it take more than about 5 pounds of force? A luggage scale hooked on the handle gives a quick reading.",
    evidence: "owner",
  },
  {
    subject: SUBJECT.door,
    section: "404.2.7",
    status: "needs_info",
    message: "What kind of handle does the front door have? A lever or push bar works; a round knob needs replacing.",
    evidence: "photo",
  },
  {
    subject: SUBJECT.door,
    section: "404.2.3",
    status: "pass",
    measured: 144.4,
    required: inches(">=", 32),
    message: "The front door opens to 144.4 inches clear, well over the 32 inches a wheelchair needs.",
    evidence: "measured",
  },
  {
    subject: SUBJECT.doorway,
    section: "403.5.1",
    status: "pass",
    measured: 78.3,
    required: inches(">=", 36),
    message: "This doorway is 78.3 inches wide, so the route through it is clear.",
    evidence: "measured",
  },
  {
    subject: SUBJECT.television,
    section: "307.2",
    status: "pass",
    measured: 3.9,
    required: inches("<=", 4),
    message: "The television sticks out 3.9 inches from the wall above 27 inches, which a cane user can pass safely.",
    evidence: "measured",
  },
];

export const SAMPLE_FINDINGS: Finding[] = SPECS.flatMap(bothCodes);

function byJurisdiction(findings: Finding[]) {
  return Object.fromEntries(["ADA2010", "CBC11B"].map((code) => [code, countStatuses(findings.filter((finding) => finding.jurisdiction === code))]));
}

export const SAMPLE_REPORT: Report = {
  scan_id: SAMPLE_SCAN_ID,
  assessment_id: "sample-assessment",
  created_at: "2026-10-14T17:21:00Z",
  summary: { total: countStatuses(SAMPLE_FINDINGS), by_jurisdiction: byJurisdiction(SAMPLE_FINDINGS) },
  findings: SAMPLE_FINDINGS,
  timings: { load_ms: 410, labelling_ms: 6200, evaluation_ms: 180, persist_ms: 95, total_ms: 6885 },
  labelled_by_vision: 3,
  unlabelled_objects: 0,
};
