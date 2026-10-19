import { afterEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_REPORT, SAMPLE_SCAN_ID, SAMPLE_SCENE } from "@/fixtures/sample";
import { ApiError, createHttpApi } from "./client";
import { liveSocketUrl } from "./config";
import { captureSteps, connectLive, fixtureMessages, INITIAL_LIVE_STATE, liveFindings, parseServerMessage, reduceLive, replayMessages } from "./live";
import type { ServerMessage } from "./types";

function jsonResponse(status: number, body: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function fakeFetch(status: number, body?: unknown) {
  return vi.fn<(url: string | URL | Request, init?: RequestInit) => Promise<Response>>(async () => jsonResponse(status, body));
}

describe("http client", () => {
  it("calls sp-server paths with the bearer token", async () => {
    const fetch = fakeFetch(200, []);
    const api = createHttpApi({ baseUrl: "https://api.test", token: "t0k", fetch });
    await api.listScans();
    await api.getReport("a b");
    const [url, init] = fetch.mock.calls[1]!;
    expect(fetch.mock.calls[0]![0]).toBe("https://api.test/v1/scans");
    expect(url).toBe("https://api.test/v1/scans/a%20b/assessment");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer t0k");
  });

  it("posts the login body as json", async () => {
    const fetch = fakeFetch(200, { token: "x", expires_at: "", user: {} });
    await createHttpApi({ baseUrl: "https://api.test", fetch }).login("a@b.c", "pw");
    const [, init] = fetch.mock.calls[0]!;
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ email: "a@b.c", password: "pw" });
    expect(new Headers(init?.headers).get("Authorization")).toBeNull();
  });

  it("turns a 404 into null and other failures into ApiError", async () => {
    expect(await createHttpApi({ baseUrl: "", fetch: fakeFetch(404, { error: "not_found", message: "Not found" }) }).getScan("x")).toBeNull();
    const failing = createHttpApi({ baseUrl: "", fetch: fakeFetch(401, { error: "unauthorized", message: "Sign in" }) });
    const error = await failing.listScans().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).unauthorized).toBe(true);
    expect((error as ApiError).message).toBe("Sign in");
  });

  it("builds the viewer socket url", () => {
    expect(liveSocketUrl("https://api.test", "s1", "tok")).toBe("wss://api.test/v1/scans/s1/live?role=viewer&token=tok");
  });
});

describe("live reducer", () => {
  const messages = fixtureMessages(SAMPLE_SCAN_ID, SAMPLE_SCENE, SAMPLE_REPORT);

  it("replays a scan in order: hello, rooms that grow, then the report", () => {
    expect(messages[0]!.type).toBe("hello");
    expect(messages.at(-1)!.type).toBe("report");
    expect(messages.filter((m) => m.type === "room")).toHaveLength(captureSteps(SAMPLE_SCENE).length);
  });

  it("folds messages into a finished state with every finding", () => {
    const states = messages.map((_, index) => messages.slice(0, index + 1).reduce(reduceLive, INITIAL_LIVE_STATE));
    const midway = states.find((state) => state.scene.rooms[0]?.walls.length === SAMPLE_SCENE.rooms[0]!.walls.length);
    expect(midway?.phase).toBe("live");
    const final = states.at(-1)!;
    expect(final.phase).toBe("finished");
    expect(liveFindings(final)).toHaveLength(SAMPLE_REPORT.findings.length);
    expect(final.scene.rooms[0]!.objects).toHaveLength(SAMPLE_SCENE.rooms[0]!.objects.length);
  });

  it("keeps findings per room and records errors", () => {
    const summary = SAMPLE_REPORT.summary;
    let state = reduceLive(INITIAL_LIVE_STATE, { type: "findings", room_id: "a", seq: 1, final: false, findings: SAMPLE_REPORT.findings.slice(0, 2), summary, elapsed_ms: 1 });
    state = reduceLive(state, { type: "findings", room_id: "b", seq: 2, final: false, findings: SAMPLE_REPORT.findings.slice(0, 1), summary, elapsed_ms: 1 });
    state = reduceLive(state, { type: "findings", room_id: "a", seq: 3, final: false, findings: [], summary, elapsed_ms: 1 });
    expect(liveFindings(state)).toHaveLength(1);
    expect(reduceLive(state, { type: "error", message: "Lost it" }).error).toBe("Lost it");
  });

  it("ignores unknown or malformed messages", () => {
    expect(parseServerMessage("not json")).toBeNull();
    expect(parseServerMessage(JSON.stringify({ type: "mystery" }))).toBeNull();
    expect(parseServerMessage(JSON.stringify({ type: "pong" }))).toEqual({ type: "pong" });
  });
});

class FakeSocket {
  static opened: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { reason: string }) => void) | null = null;
  closed = false;
  constructor(readonly url: string) {
    FakeSocket.opened.push(this);
  }
  close() {
    this.closed = true;
  }
}

describe("live socket", () => {
  afterEach(() => {
    vi.useRealTimers();
    FakeSocket.opened = [];
  });

  it("reconnects with backoff and stops after the report", () => {
    vi.useFakeTimers();
    const received: ServerMessage[] = [];
    const onClosed = vi.fn();
    connectLive("ws://x", { onMessage: (m) => received.push(m), onClosed }, (url) => new FakeSocket(url) as unknown as WebSocket);
    FakeSocket.opened[0]!.onclose!({ reason: "" });
    vi.advanceTimersByTime(500);
    expect(FakeSocket.opened).toHaveLength(2);
    const socket = FakeSocket.opened[1]!;
    socket.onmessage!({ data: JSON.stringify({ type: "report", report: SAMPLE_REPORT }) });
    socket.onclose!({ reason: "" });
    vi.advanceTimersByTime(10_000);
    expect(FakeSocket.opened).toHaveLength(2);
    expect(received.map((m) => m.type)).toEqual(["report"]);
    expect(onClosed).not.toHaveBeenCalled();
  });

  it("gives up after the last retry", () => {
    vi.useFakeTimers();
    const onClosed = vi.fn();
    connectLive("ws://x", { onMessage: () => undefined, onClosed }, (url) => new FakeSocket(url) as unknown as WebSocket);
    for (let attempt = 0; attempt < 6; attempt += 1) {
      FakeSocket.opened.at(-1)!.onclose!({ reason: "gone" });
      vi.advanceTimersByTime(8000);
    }
    expect(onClosed).toHaveBeenCalledWith("gone");
  });

  it("replays fixture messages on a timer until closed", () => {
    vi.useFakeTimers();
    const received: string[] = [];
    const replay = replayMessages([{ type: "pong" }, { type: "pong" }, { type: "pong" }], { onMessage: (m) => received.push(m.type) }, 300);
    vi.advanceTimersByTime(260);
    expect(received).toHaveLength(2);
    replay.close();
    vi.advanceTimersByTime(1000);
    expect(received).toHaveLength(2);
  });
});
