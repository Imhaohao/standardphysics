import type { Room, Scene } from "@/lib/scene/types";
import type { components } from "./openapi.gen";

/** Wire types for sp-server's /v1 API, generated from server/openapi.json by `pnpm api:types`. */
type Schemas = components["schemas"];

export type ScanStatus = "capturing" | "finishing" | "complete" | "failed";
export type Scan = Schemas["Scan"];
export type StageTimings = Schemas["StageTimings"];
export type Report = Schemas["Report"];
export type User = Schemas["User"];
export type AuthResponse = Schemas["AuthResponse"];
export type LiveTicket = Schemas["LiveTicket"];

type GeneratedMessage = Schemas["ServerMessage"];

/** The live socket's frames. OpenAPI types `room` and `scene` as plain objects; they carry sp-core's Room and Scene. */
export type ServerMessage =
  | Exclude<GeneratedMessage, { type: "room" | "scene" }>
  | { type: "room"; room: Room }
  | { type: "scene"; scene: Scene };
