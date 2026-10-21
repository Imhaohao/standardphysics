import type { Finding } from "@/lib/findings/types";
import type { Room, Scene } from "@/lib/scene/types";
import type { components } from "./openapi.gen";

/** Wire types for sp-server's /v1 API, generated from server/openapi.json by `pnpm api:types`. */
type Schemas = components["schemas"];

export type ScanStatus = "capturing" | "finishing" | "complete" | "failed";
export type Scan = Schemas["Scan"];
export type StageTimings = Schemas["StageTimings"];
export type Report = Omit<Schemas["Report"], "findings"> & { findings: Finding[] };
export type User = Schemas["User"];
export type AuthResponse = Schemas["AuthResponse"];
export type LiveTicket = Schemas["LiveTicket"];

type GeneratedMessage = Schemas["ServerMessage"];

/** The live socket's frames. OpenAPI types `room` and `scene` as plain objects; they carry sp-core's Room and Scene. */
export type ServerMessage =
  | Exclude<GeneratedMessage, { type: "room" | "scene" }>
  | { type: "room"; room: Room }
  | { type: "scene"; scene: Scene };

/*
 * The types below follow the answers, scan editing, account and sharing routes that sp-server is gaining. They are
 * written by hand until server/openapi.json describes those routes, and then they move to generated types.
 */

/** An owner's answer. Sending `null` as the value deletes the answer. */
export type AnswerValue = boolean | number | string | null;

export interface AnswerInput {
  subject_id: string;
  metric: string;
  value: AnswerValue;
}

export interface Answer extends AnswerInput {
  answered_at: string;
}

export interface ScanChanges {
  name?: string;
  site_name?: string | null;
}

/** A read-only link to a scan's report, opened at /r/{token}. */
export interface Share {
  token: string;
  created_at: string;
}

/** What a read-only link shows to someone who isn't signed in. */
export interface SharedShop {
  scan: Scan;
  report: Report;
  scene: Scene | null;
}
