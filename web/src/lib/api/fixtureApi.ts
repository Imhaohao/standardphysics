import { SAMPLE_REPORT, SAMPLE_SCAN_ID, SAMPLE_SCANS, SAMPLE_SCENE } from "@/fixtures/sample";
import type { Api } from "./client";

const isSample = (scanId: string) => scanId === SAMPLE_SCAN_ID;

/** Answers every API call from the bundled sample shop, so the site runs with no backend. */
export const fixtureApi: Api = {
  login: async (email) => ({ token: "fixture-token", expires_at: "2099-01-01T00:00:00Z", user: { id: "fixture-user", email } }),
  logout: async () => undefined,
  listScans: async () => SAMPLE_SCANS,
  getScan: async (scanId) => SAMPLE_SCANS.find((scan) => scan.id === scanId) ?? null,
  getScene: async (scanId) => (isSample(scanId) ? SAMPLE_SCENE : null),
  getReport: async (scanId) => (isSample(scanId) ? SAMPLE_REPORT : null),
  createLiveTicket: async () => {
    throw new Error("The sample shop is replayed, so it has no live socket.");
  },
};
