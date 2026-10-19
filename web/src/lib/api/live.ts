import { countStatuses } from "@/lib/findings/group";
import type { Finding, FindingsSummary } from "@/lib/findings/types";
import type { Room, Scene } from "@/lib/scene/types";
import type { Report, ServerMessage } from "./types";

export type LivePhase = "connecting" | "live" | "finished" | "error";

/** What the live view knows about a scan in progress, folded from the server's messages. */
export interface LiveState {
  phase: LivePhase;
  scene: Scene;
  findingsByRoom: Record<string, Finding[]>;
  summary: FindingsSummary | null;
  report: Report | null;
  error: string | null;
}

export const EMPTY_SCENE: Scene = { version: 2, rooms: [], connections: [], observations: [] };

export const INITIAL_LIVE_STATE: LiveState = { phase: "connecting", scene: EMPTY_SCENE, findingsByRoom: {}, summary: null, report: null, error: null };

const ALL_ROOMS = "*";

function upsertRoom(scene: Scene, room: Room): Scene {
  const rooms = scene.rooms.some((existing) => existing.id === room.id)
    ? scene.rooms.map((existing) => (existing.id === room.id ? room : existing))
    : [...scene.rooms, room];
  return { ...scene, rooms };
}

type Reducer<T extends ServerMessage["type"]> = (state: LiveState, message: Extract<ServerMessage, { type: T }>) => LiveState;

const REDUCERS: { [T in ServerMessage["type"]]: Reducer<T> } = {
  hello: (state, message) => ({ ...state, phase: "live", findingsByRoom: { [ALL_ROOMS]: message.findings }, summary: message.summary }),
  findings: (state, message) => {
    const rooms = Object.fromEntries(Object.entries(state.findingsByRoom).filter(([room]) => room !== ALL_ROOMS));
    return { ...state, phase: "live", findingsByRoom: { ...rooms, [message.room_id]: message.findings }, summary: message.summary };
  },
  report: (state, message) => ({ ...state, phase: "finished", report: message.report, findingsByRoom: { [ALL_ROOMS]: message.report.findings }, summary: message.report.summary }),
  error: (state, message) => ({ ...state, error: message.message }),
  pong: (state) => state,
  room: (state, message) => ({ ...state, phase: "live", scene: upsertRoom(state.scene, message.room) }),
  scene: (state, message) => ({ ...state, scene: message.scene }),
};

export function reduceLive(state: LiveState, message: ServerMessage): LiveState {
  const reducer = REDUCERS[message.type] as Reducer<ServerMessage["type"]> | undefined;
  return reducer ? reducer(state, message) : state;
}

export function liveFindings(state: LiveState): Finding[] {
  return Object.values(state.findingsByRoom).flat();
}

export function parseServerMessage(text: string): ServerMessage | null {
  try {
    const message = JSON.parse(text) as { type?: unknown };
    return typeof message.type === "string" && message.type in REDUCERS ? (message as ServerMessage) : null;
  } catch {
    return null;
  }
}

export interface LiveConnection {
  close(): void;
}

export interface LiveHandlers {
  onMessage(message: ServerMessage): void;
  onClosed(reason: string): void;
}

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000];

/** Subscribes read-only to a scan's live socket, reconnecting with backoff until closed or the scan finishes. */
export function connectLive(url: string, handlers: LiveHandlers, createSocket = (target: string) => new WebSocket(target)): LiveConnection {
  let socket: WebSocket | null = null;
  let attempt = 0;
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    socket = createSocket(url);
    socket.onopen = () => (attempt = 0);
    socket.onmessage = (event) => {
      const message = typeof event.data === "string" ? parseServerMessage(event.data) : null;
      if (!message) return;
      handlers.onMessage(message);
      if (message.type === "report") closed = true;
    };
    socket.onclose = (event) => {
      if (closed) return;
      const delay = RECONNECT_DELAYS_MS[attempt];
      if (delay === undefined) return handlers.onClosed(event.reason || "The live connection dropped.");
      attempt += 1;
      timer = setTimeout(open, delay);
    };
  };

  open();
  return {
    close() {
      closed = true;
      clearTimeout(timer);
      socket?.close();
    },
  };
}

/** Partial copies of a scene, one more element each, in the order a scan would find them: walls, then doors, then furniture. */
export function captureSteps(scene: Scene): Room[] {
  return scene.rooms.flatMap((room) => {
    const empty: Room = { ...room, walls: [], openings: [], objects: [] };
    const steps: Room[] = [];
    let current = empty;
    const add = (next: Partial<Room>) => {
      current = { ...current, ...next };
      steps.push(current);
    };
    room.walls.forEach((_, index) => add({ walls: room.walls.slice(0, index + 1) }));
    room.openings.forEach((_, index) => add({ openings: room.openings.slice(0, index + 1) }));
    room.objects.forEach((_, index) => add({ objects: room.objects.slice(0, index + 1) }));
    return steps;
  });
}

function knownIds(room: Room) {
  return new Set([room.id, ...room.walls.map((w) => w.id), ...room.openings.map((o) => o.id), ...room.objects.map((o) => o.id)]);
}

function summaryOf(findings: Finding[]): FindingsSummary {
  const byCode = (code: string) => countStatuses(findings.filter((finding) => finding.jurisdiction === code));
  return { total: countStatuses(findings), by_jurisdiction: { ADA2010: byCode("ADA2010"), CBC11B: byCode("CBC11B") } };
}

/** The messages a scan of `scene` would produce, for fixture mode: each capture step, then the findings it unlocks. */
export function fixtureMessages(scanId: string, scene: Scene, report: Report): ServerMessage[] {
  const messages: ServerMessage[] = [{ type: "hello", scan_id: scanId, rooms: [], findings: [], summary: summaryOf([]) }];
  const reported = new Set<Finding>();
  for (const room of captureSteps(scene)) {
    messages.push({ type: "room", room });
    const ids = knownIds(room);
    const visible = report.findings.filter((finding) => ids.has(finding.subject_id));
    if (visible.every((finding) => reported.has(finding))) continue;
    visible.forEach((finding) => reported.add(finding));
    messages.push({ type: "findings", room_id: room.id, seq: messages.length, final: false, findings: visible, summary: summaryOf(visible), elapsed_ms: 40 });
  }
  messages.push({ type: "report", report });
  return messages;
}

/** Plays fixture messages out on a timer, as if a scan were happening now. */
export function replayMessages(messages: ServerMessage[], handlers: Pick<LiveHandlers, "onMessage">, intervalMs: number): LiveConnection {
  let index = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const next = () => {
    const message = messages[index++];
    if (!message) return;
    handlers.onMessage(message);
    timer = setTimeout(next, message.type === "room" ? intervalMs : intervalMs / 3);
  };
  timer = setTimeout(next, intervalMs / 2);
  return { close: () => clearTimeout(timer) };
}
