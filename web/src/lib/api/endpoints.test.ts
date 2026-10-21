import { describe, expect, it, vi } from "vitest";
import { SAMPLE_SCAN_ID } from "@/fixtures/sample";
import { createHttpApi } from "./client";
import { createFixtureApi } from "./fixtureApi";

function recordingFetch(status: number, body?: unknown) {
  return vi.fn<(url: string | URL | Request, init?: RequestInit) => Promise<Response>>(
    async () => new Response(body === null ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

async function callOf(run: (api: ReturnType<typeof createHttpApi>) => Promise<unknown>, status = 200, body: unknown = {}) {
  const fetch = recordingFetch(status, body);
  await run(createHttpApi({ baseUrl: "https://api.test", token: "t0k", fetch }));
  const [url, init] = fetch.mock.calls[0]!;
  return { url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined, headers: new Headers(init?.headers) };
}

describe("http client, account and scan routes", () => {
  it("registers with the same body as login", async () => {
    expect(await callOf((api) => api.register("a@b.c", "longenough"), 201)).toMatchObject({ url: "https://api.test/v1/auth/register", method: "POST", body: { email: "a@b.c", password: "longenough" } });
  });

  it("deletes the account and scans, and patches a scan's names", async () => {
    expect(await callOf((api) => api.deleteAccount(), 204, null)).toMatchObject({ url: "https://api.test/v1/me", method: "DELETE" });
    expect(await callOf((api) => api.deleteScan("s1"), 204, null)).toMatchObject({ url: "https://api.test/v1/scans/s1", method: "DELETE" });
    expect(await callOf((api) => api.updateScan("s1", { name: "Front", site_name: null }))).toMatchObject({ url: "https://api.test/v1/scans/s1", method: "PATCH", body: { name: "Front", site_name: null } });
  });

  it("puts answers wrapped in an answers object", async () => {
    const answers = [{ subject_id: "door-1", metric: "door.has_latch", value: true }];
    const call = await callOf((api) => api.saveAnswers("s1", answers), 200, { findings: [] });
    expect(call).toMatchObject({ url: "https://api.test/v1/scans/s1/answers", method: "PUT", body: { answers } });
    expect(call.headers.get("Content-Type")).toBe("application/json");
  });
});

describe("http client, sharing routes", () => {
  it("creates, lists and stops shares under the scan", async () => {
    expect(await callOf((api) => api.createShare("s1"), 201, { token: "t", created_at: "" })).toMatchObject({ url: "https://api.test/v1/scans/s1/shares", method: "POST" });
    expect(await callOf((api) => api.listShares("s1"), 200, [])).toMatchObject({ url: "https://api.test/v1/scans/s1/shares", method: "GET" });
    expect(await callOf((api) => api.deleteShare("s1", "a-b_c"), 204, null)).toMatchObject({ url: "https://api.test/v1/scans/s1/shares/a-b_c", method: "DELETE" });
  });

  it("reads a shared report without a session and turns a revoked link into null", async () => {
    const fetch = recordingFetch(404, { error: "not_found", message: "gone" });
    expect(await createHttpApi({ baseUrl: "https://api.test", fetch }).getShared("tok")).toBeNull();
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("https://api.test/v1/shared/tok");
    expect(new Headers(init?.headers).get("Authorization")).toBeNull();
  });
});

describe("fixture api", () => {
  it("adds asks to the sample's open questions and settles them once answered", async () => {
    const api = createFixtureApi();
    const asked = (await api.getReport(SAMPLE_SCAN_ID))!.findings.filter((finding) => finding.ask);
    expect(asked.length).toBeGreaterThan(0);
    const fireDoor = asked.find((finding) => finding.ask!.metric === "door.is_fire_door")!;
    const report = await api.saveAnswers(SAMPLE_SCAN_ID, [{ subject_id: fireDoor.subject_id, metric: "door.is_fire_door", value: true }]);
    const after = report.findings.filter((finding) => finding.subject_id === fireDoor.subject_id && finding.rule_id === fireDoor.rule_id);
    expect(after[0]).toMatchObject({ status: "not_applicable", ask: null });
    expect(await api.listAnswers(SAMPLE_SCAN_ID)).toHaveLength(1);
    await api.saveAnswers(SAMPLE_SCAN_ID, [{ subject_id: fireDoor.subject_id, metric: "door.is_fire_door", value: null }]);
    expect(await api.listAnswers(SAMPLE_SCAN_ID)).toHaveLength(0);
  });

  it("shares the sample until the link is stopped", async () => {
    const api = createFixtureApi();
    const share = await api.createShare(SAMPLE_SCAN_ID);
    expect(share.token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect((await api.getShared(share.token))?.scan.id).toBe(SAMPLE_SCAN_ID);
    await api.deleteShare(SAMPLE_SCAN_ID, share.token);
    expect(await api.getShared(share.token)).toBeNull();
  });

  it("renames and deletes the sample scan in memory only", async () => {
    const api = createFixtureApi();
    expect((await api.updateScan(SAMPLE_SCAN_ID, { site_name: "Corner cafe" })).site_name).toBe("Corner cafe");
    await api.deleteScan(SAMPLE_SCAN_ID);
    expect(await api.getScan(SAMPLE_SCAN_ID)).toBeNull();
    expect(await api.getReport(SAMPLE_SCAN_ID)).toBeNull();
    expect((await createFixtureApi().getScan(SAMPLE_SCAN_ID))?.site_name).toBe("Corner shop");
  });
});
