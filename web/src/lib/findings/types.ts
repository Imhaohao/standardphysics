import type { components } from "@/lib/api/openapi.gen";

/** The Finding contract, generated from server/openapi.json (which mirrors sp-core). Measurements use rules/metrics.json units. */
type Schemas = components["schemas"];

export type FindingStatus = Schemas["FindingStatus"];
export type Jurisdiction = "ADA2010" | "CBC11B";
export type Measured = Schemas["Measured"];
export type StatusCounts = Schemas["StatusCounts"];
export type Governing = Schemas["Governing"];
export type FindingsSummary = Schemas["Summary"];

export type AskValueType = "boolean" | "number" | "integer" | "enum";

/**
 * What the owner can answer to settle a needs_info finding. It is written by hand until server/openapi.json
 * carries it: sp-core attaches one to a finding that is only missing an owner or photo answer.
 */
export interface Ask {
  /** The metric id the answer is stored under, from rules/metrics.json. */
  metric: string;
  prompt: string;
  value_type: AskValueType;
  /** For numbers, a rules/metrics.json unit such as "in" or "lbf". */
  unit: string;
  /** The allowed values of an enum, otherwise empty. */
  options: string[];
  /** The rule would rather see a photo, though the owner's answer still counts. */
  photo: boolean;
  subject_id?: string;
}

export type Finding = Schemas["Finding"] & { ask?: Ask | null };
