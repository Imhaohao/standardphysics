import type { Assessment, Report, Scan, ScanList, Scenario, SceneGraph } from "@/types/contracts";
import { API_ORIGIN } from "./api-origin";

export class NotReady extends Error {}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_ORIGIN}${path}`, { cache: "no-store" });
  if (response.status === 404) throw new NotReady(path);
  if (!response.ok) throw new Error(`${path} answered ${response.status}`);
  return (await response.json()) as T;
}

async function getOptional<T>(path: string): Promise<T | null> {
  try {
    return await getJson<T>(path);
  } catch (error) {
    if (error instanceof NotReady) return null;
    throw error;
  }
}

export const listScans = async () => (await getJson<ScanList>("/api/scans")).scans;
export const getScan = (scanId: string) => getOptional<Scan>(`/api/scans/${scanId}`);
export const getScene = (scanId: string, revision?: number) =>
  getOptional<SceneGraph>(`/api/scans/${scanId}/scene${revision === undefined ? "" : `?revision=${revision}`}`);
export const getScenario = (scanId: string) => getOptional<Scenario>(`/api/scans/${scanId}/scenario`);
export const getAssessment = (scanId: string, revision?: number) =>
  getOptional<Assessment>(`/api/scans/${scanId}/assessment${revision === undefined ? "" : `?revision=${revision}`}`);

export const sceneGlbUrl = (scanId: string, revision?: number) => `/api/scans/${scanId}/scene.glb${revision === undefined ? "" : `?revision=${revision}`}`;
export const getReport = (scanId: string) => getOptional<Report>(`/api/scans/${scanId}/report`);
export const getScenarioSuggestion = (scanId: string) => getOptional<Scenario>(`/api/scans/${scanId}/scenario/suggestion`);
