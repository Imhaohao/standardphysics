import type { Finding, FindingsSummary } from "@/lib/findings/types";
import type { Room, Scene } from "@/lib/scene/types";

/** Wire types for sp-server's /v1 API (server/src/scans/models.rs, auth/models.rs, live/protocol.rs). */
export type ScanStatus = "capturing" | "finishing" | "complete" | "failed";

export interface Scan {
  id: string;
  name: string;
  site_name: string | null;
  status: ScanStatus | (string & {});
  created_at: string;
  updated_at: string;
}

export interface StageTimings {
  load_ms: number;
  labelling_ms: number;
  evaluation_ms: number;
  persist_ms: number;
  total_ms: number;
}

export interface Report {
  scan_id: string;
  assessment_id: string;
  created_at: string;
  summary: FindingsSummary;
  findings: Finding[];
  timings: StageTimings;
  labelled_by_vision: number;
  unlabelled_objects: number;
}

export interface User {
  id: string;
  email: string | null;
}

export interface AuthResponse {
  token: string;
  expires_at: string;
  user: User;
}

export type ServerMessage =
  | { type: "hello"; scan_id: string; rooms: string[]; findings: Finding[]; summary: FindingsSummary }
  | { type: "findings"; room_id: string; seq: number | null; final: boolean; findings: Finding[]; summary: FindingsSummary; elapsed_ms: number }
  | { type: "report"; report: Report }
  | { type: "error"; message: string }
  | { type: "pong" }
  /** Not sent by sp-server yet: room geometry as it is captured. The live view inks it the moment it arrives. */
  | { type: "room"; room: Room }
  | { type: "scene"; scene: Scene };
