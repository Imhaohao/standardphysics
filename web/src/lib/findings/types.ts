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

/** What the owner can answer to settle a needs_info finding; `value_type` outside AskValueType is not asked. */
export type Ask = Schemas["Ask"];

export type Finding = Schemas["Finding"];
