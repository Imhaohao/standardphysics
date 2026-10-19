import type { components } from "@/lib/api/openapi.gen";

/** The Finding contract, generated from server/openapi.json (which mirrors sp-core). Measurements use rules/metrics.json units. */
type Schemas = components["schemas"];

export type FindingStatus = Schemas["FindingStatus"];
export type Jurisdiction = "ADA2010" | "CBC11B";
export type Measured = Schemas["Measured"];
export type Finding = Schemas["Finding"];
export type StatusCounts = Schemas["StatusCounts"];
export type Governing = Schemas["Governing"];
export type FindingsSummary = Schemas["Summary"];
