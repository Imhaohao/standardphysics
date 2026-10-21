import { SAMPLE_REPORT, SAMPLE_SCAN_ID, SAMPLE_SCANS, SAMPLE_SCENE } from "@/fixtures/sample";
import { answerKey, sampleReportWithAnswers } from "@/fixtures/sampleAsks";
import type { Api } from "./client";
import type { Answer, AnswerInput, Scan, Share } from "./types";

/** 32 random bytes as unpadded base64url: the same 43-character shape as sp-server's share tokens. */
function shareToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function notFound(): never {
  throw new Error("The sample shop has no scan by that id.");
}

/**
 * Answers every API call from the bundled sample shop, so the site runs with no backend. Edits, answers and share
 * links live in this process's memory, so they last until the server restarts.
 */
export function createFixtureApi(): Api {
  const scans: Scan[] = SAMPLE_SCANS.map((scan) => ({ ...scan }));
  const answers = new Map<string, Answer>();
  const shares: Share[] = [];

  const findScan = (scanId: string) => scans.find((scan) => scan.id === scanId) ?? null;
  const hasSample = (scanId: string) => scanId === SAMPLE_SCAN_ID && findScan(scanId) !== null;
  const sampleReport = () => sampleReportWithAnswers(SAMPLE_REPORT, answers);

  function recordAnswer(input: AnswerInput) {
    const key = answerKey(input.subject_id, input.metric);
    if (input.value === null) answers.delete(key);
    else answers.set(key, { ...input, answered_at: new Date().toISOString(), source: "owner", confidence: 1, photo_artifact_id: null });
  }

  return {
    login: async (email) => ({ token: "fixture-token", expires_at: "2099-01-01T00:00:00Z", user: { id: "fixture-user", email } }),
    register: async (email) => ({ token: "fixture-token", expires_at: "2099-01-01T00:00:00Z", user: { id: "fixture-user", email } }),
    logout: async () => undefined,
    deleteAccount: async () => undefined,
    listScans: async () => scans.map((scan) => ({ ...scan })),
    getScan: async (scanId) => findScan(scanId),
    updateScan: async (scanId, changes) => {
      const scan = findScan(scanId) ?? notFound();
      Object.assign(scan, changes, { updated_at: new Date().toISOString() });
      return { ...scan };
    },
    deleteScan: async (scanId) => {
      scans.splice(scans.indexOf(findScan(scanId) ?? notFound()), 1);
      shares.length = 0;
    },
    getScene: async (scanId) => (hasSample(scanId) ? SAMPLE_SCENE : null),
    getReport: async (scanId) => (hasSample(scanId) ? sampleReport() : null),
    listAnswers: async () => [...answers.values()],
    saveAnswers: async (scanId, inputs) => {
      if (!hasSample(scanId)) notFound();
      inputs.forEach(recordAnswer);
      return sampleReport();
    },
    createLiveTicket: async () => {
      throw new Error("The sample shop is replayed, so it has no live socket.");
    },
    createShare: async (scanId) => {
      if (!hasSample(scanId)) notFound();
      const share = { token: shareToken(), created_at: new Date().toISOString() };
      shares.push(share);
      return share;
    },
    listShares: async (scanId) => (hasSample(scanId) ? [...shares] : []),
    deleteShare: async (_scanId, token) => {
      const index = shares.findIndex((share) => share.token === token);
      if (index >= 0) shares.splice(index, 1);
    },
    getShared: async (token) => {
      const scan = findScan(SAMPLE_SCAN_ID);
      if (!scan || !shares.some((share) => share.token === token)) return null;
      return { scan, report: sampleReport(), scene: SAMPLE_SCENE };
    },
  };
}

export const fixtureApi: Api = createFixtureApi();
