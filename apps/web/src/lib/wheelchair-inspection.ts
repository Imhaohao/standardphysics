import type { SceneNode } from "@/types/contracts";

export const INCHES_PER_METER = 39.3701;

export const ADA_RULES = [
  {
    section: "902.3",
    label: "Dining and work-surface height",
    url: "https://www.ada.gov/law-and-regs/design-standards/2010-stds/#902-dining-surfaces-and-work-surfaces",
    caveat: "Applies only to an applicable dining or work surface; it requires a measured top above the finished floor.",
  },
  {
    section: "306",
    label: "Knee and toe clearance",
    url: "https://www.ada.gov/law-and-regs/design-standards/2010-stds/#306-knee-and-toe-clearance",
    caveat: "Requires measured underside and clearance geometry; object bounds do not show it.",
  },
  {
    section: "308",
    label: "Reach ranges",
    url: "https://www.ada.gov/law-and-regs/design-standards/2010-stds/#308-reach-ranges",
    caveat: "Depends on reach type, obstructions, and the operable part location; center distance is context only.",
  },
] as const;

export type InspectionCategory =
  | "dining_or_work_candidate"
  | "service_or_sales_counter"
  | "unclassified_counter"
  | "seat"
  | "outlet"
  | "candidate_outlet"
  | "object";

const ELECTRICAL = /(outlet|receptacle|power strip)/;

/** What the words attached to a region suggest it is, tried in order. */
const WORD_CATEGORIES: [RegExp, InspectionCategory][] = [
  [/(table|desk|work surface|dining)/, "dining_or_work_candidate"],
  [/(chair|sofa|stool|seat)/, "seat"],
];

/** A counter is a service counter when the words say who it serves. */
function counterCategory(words: string): InspectionCategory {
  return /(service|sales|checkout|cashier|ordering)/.test(words)
    ? "service_or_sales_counter"
    : "unclassified_counter";
}

export function inspectionCategory(node: SceneNode): InspectionCategory {
  if (node.kind === "outlet" || node.kind === "candidate_outlet") return node.kind;

  const words = `${node.raw_category} ${node.label}`.toLowerCase();
  if (ELECTRICAL.test(words)) return "outlet";
  if (words.includes("counter")) return counterCategory(words);

  const matched = WORD_CATEGORIES.find(([pattern]) => pattern.test(words));
  return matched ? matched[1] : "object";
}

export function inspectionCategoryLabel(category: InspectionCategory) {
  switch (category) {
    case "outlet":
      return "Photographed electrical outlet";
    case "candidate_outlet":
      return "Candidate electrical outlet (needs verification)";
    case "dining_or_work_candidate":
      return "Dining/work-surface candidate";
    case "service_or_sales_counter":
      return "Service/sales counter candidate";
    case "unclassified_counter":
      return "Counter category not established";
    case "seat":
      return "Seat candidate";
    default:
      return "Object";
  }
}

export function boundsEstimate(node: SceneNode) {
  return {
    widthInches: node.dimensions.x * INCHES_PER_METER,
    depthInches: node.dimensions.y * INCHES_PER_METER,
    heightInches: node.dimensions.z * INCHES_PER_METER,
  };
}

export function inspectionLimitations(category: InspectionCategory) {
  if (category === "outlet" || category === "candidate_outlet") {
    return [
      "Electrical power, circuit live status, and socket condition are not established.",
      "Plug insertion ability, grip strength, and dexterity are not established.",
      "ADA compliance is not established.",
      "Requires verified route approach and reach envelope.",
    ];
  }

  const common = [
    "No measured operable part or reach path.",
    "No measured knee or toe clearance.",
  ];

  if (category === "dining_or_work_candidate") {
    return ["No measured tabletop height above finished floor.", ...common];
  }
  if (category === "service_or_sales_counter" || category === "unclassified_counter") {
    return ["Counter use and applicable rule are not established by the scan category.", ...common];
  }
  if (category === "seat") return ["No measured seat height.", ...common];
  return common;
}

export function isDockableInspectionTarget(category: InspectionCategory) {
  return category === "dining_or_work_candidate"
    || category === "service_or_sales_counter"
    || category === "unclassified_counter"
    || category === "outlet"
    || category === "candidate_outlet";
}
