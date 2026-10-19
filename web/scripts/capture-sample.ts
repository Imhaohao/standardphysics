/**
 * Runs the bundled RoomPlan capture through a real sp-server: signs up, creates a scan, streams the room over the
 * live socket one surface at a time, finishes the scan and fetches the scene and assessment.
 *
 *   node --experimental-strip-types scripts/capture-sample.ts [--api http://localhost:8080] [--pace 400] [--write] [--scan <id>]
 *
 * --write saves the server's scene and report as the fixture-mode sample. --scan streams into an existing scan.
 * Prints the scan id and session token as JSON on the last line.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

type Json = Record<string, unknown>;

const { values: args } = parseArgs({
  options: {
    api: { type: "string", default: "http://localhost:8080" },
    pace: { type: "string", default: "0" },
    write: { type: "boolean", default: false },
    scan: { type: "string" },
    email: { type: "string", default: "owner@corner.shop" },
    password: { type: "string", default: "corner-shop-sample" },
  },
});

const fixture = (path: string) => fileURLToPath(new URL(path, import.meta.url));
const capture = JSON.parse(readFileSync(fixture("../fixtures/roomplan/apple_livingroom.room.json"), "utf8")) as Json;
const ROOM_ID = "living-room";
const SAMPLE_SCAN_ID = "sample-living-room";

async function call<T>(path: string, init: RequestInit & { token?: string } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (init.token) headers.set("Authorization", `Bearer ${init.token}`);
  const response = await fetch(`${args.api}/v1${path}`, { ...init, headers });
  if (!response.ok) throw new Error(`${init.method ?? "GET"} ${path} answered ${response.status}: ${await response.text()}`);
  return (await response.json()) as T;
}

async function signIn() {
  const body = JSON.stringify({ email: args.email, password: args.password });
  try {
    return await call<{ token: string }>("/auth/register", { method: "POST", body });
  } catch {
    return call<{ token: string }>("/auth/login", { method: "POST", body });
  }
}

/** Copies of the capture that grow one surface at a time: walls, then doors and openings, then furniture. */
function progressiveCaptures(full: Json): Json[] {
  const kinds = ["walls", "doors", "openings", "windows", "objects"] as const;
  const empty: Json = { ...full, ...Object.fromEntries(kinds.map((kind) => [kind, []])) };
  const steps: Json[] = [];
  let current = empty;
  for (const kind of kinds) {
    const items = (full[kind] as unknown[] | undefined) ?? [];
    items.forEach((_, index) => {
      current = { ...current, [kind]: items.slice(0, index + 1) };
      steps.push(current);
    });
  }
  return steps;
}

async function openSocket(scanId: string, token: string) {
  const { ticket } = await call<{ ticket: string }>(`/scans/${scanId}/live-ticket`, { method: "POST", token });
  const url = new URL(`/v1/scans/${scanId}/live`, args.api);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("ticket", ticket);
  const socket = new WebSocket(url);
  const received: Json[] = [];
  const waiters: { type: string; resolve: (message: Json) => void }[] = [];
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data)) as Json;
    received.push(message);
    for (const waiter of waiters.filter((w) => w.type === message.type)) {
      waiters.splice(waiters.indexOf(waiter), 1);
      waiter.resolve(message);
    }
  });
  const next = (type: string) => new Promise<Json>((resolve) => waiters.push({ type, resolve }));
  const opened = new Promise<void>((resolve, reject) => {
    socket.addEventListener("open", () => resolve());
    socket.addEventListener("error", () => reject(new Error(`Could not open ${url}`)));
  });
  return { socket, received, next, opened };
}

/** JSON with numbers rounded, so float noise from storage (last-digit jsonb round trips) neither shows in diffs nor counts as a change. */
function stable(value: unknown, digits = 1e4) {
  return JSON.stringify(value, (_, v: unknown) => (typeof v === "number" ? Math.round(v * digits) / digits : v), 2);
}

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function asSample(report: Json) {
  return { ...report, scan_id: SAMPLE_SCAN_ID };
}

async function main() {
  const { token } = await signIn();
  const scanId = args.scan ?? (await call<{ id: string }>("/scans", { method: "POST", token, body: JSON.stringify({ name: "Corner shop", site_name: "Corner shop" }) })).id;
  console.error(`scan ${scanId}`);

  const live = await openSocket(scanId, token);
  const hello = live.next("hello");
  await live.opened;
  await hello;

  const pace = Number(args.pace);
  const steps = pace > 0 ? progressiveCaptures(capture) : [capture];
  for (const [index, step] of steps.entries()) {
    const findings = live.next("findings");
    live.socket.send(JSON.stringify({ type: "room", room_id: ROOM_ID, final: index === steps.length - 1, seq: index + 1, captured_room: step, observations: [] }));
    await findings;
    if (pace > 0) await pause(pace);
  }

  const report = await call<Json>(`/scans/${scanId}/finish`, { method: "POST", token });
  const scene = await call<Json>(`/scans/${scanId}/scene`, { token });
  const assessment = await call<Json>(`/scans/${scanId}/assessment`, { token });
  live.socket.close();

  const types = live.received.map((message) => message.type);
  console.error(`socket frames: ${[...new Set(types)].map((type) => `${type}×${types.filter((t) => t === type).length}`).join(" ")}`);
  const [finished, stored] = [report.findings as Json[], assessment.findings as Json[]];
  const differing = finished.findIndex((finding, index) => stable(finding, 1e9) !== stable(stored[index], 1e9));
  console.error(`findings: ${finished.length}, stored assessment ${differing < 0 ? "matches finish" : `differs from finish at ${differing}:\n${JSON.stringify(finished[differing])}\n${JSON.stringify(stored[differing])}`}`);

  if (args.write) {
    writeFileSync(fixture("../src/fixtures/sample-scene.json"), `${stable(scene)}\n`);
    writeFileSync(fixture("../src/fixtures/sample-report.json"), `${stable(asSample(assessment))}\n`);
    console.error("wrote src/fixtures/sample-scene.json and sample-report.json");
  }
  console.log(JSON.stringify({ scanId, token }));
}

await main();
