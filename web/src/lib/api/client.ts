import type { Scene } from "@/lib/scene/types";
import { apiBaseUrl, isFixtureMode } from "./config";
import { fixtureApi } from "./fixtureApi";
import type { Answer, AnswerInput, AuthResponse, LiveTicket, Report, Scan, ScanChanges, Share, SharedShop } from "./types";

/** Everything the web app asks of sp-server. Pages talk to this interface only. */
export interface Api {
  login(email: string, password: string): Promise<AuthResponse>;
  register(email: string, password: string): Promise<AuthResponse>;
  logout(): Promise<void>;
  deleteAccount(): Promise<void>;
  listScans(): Promise<Scan[]>;
  getScan(scanId: string): Promise<Scan | null>;
  updateScan(scanId: string, changes: ScanChanges): Promise<Scan>;
  deleteScan(scanId: string): Promise<void>;
  getScene(scanId: string): Promise<Scene | null>;
  getReport(scanId: string): Promise<Report | null>;
  listAnswers(scanId: string): Promise<Answer[]>;
  /** Stores the answers and returns the report re-evaluated with them. */
  saveAnswers(scanId: string, answers: AnswerInput[]): Promise<Report>;
  createLiveTicket(scanId: string): Promise<LiveTicket>;
  createShare(scanId: string): Promise<Share>;
  listShares(scanId: string): Promise<Share[]>;
  deleteShare(scanId: string, token: string): Promise<void>;
  /** A read-only link's scan and report. It needs no session, and a revoked or unknown token is null. */
  getShared(token: string): Promise<SharedShop | null>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get unauthorized() {
    return this.status === 401;
  }
}

export interface HttpApiOptions {
  baseUrl: string;
  token?: string | null;
  fetch?: typeof fetch;
}

async function errorFrom(response: Response) {
  const body = (await response.json().catch(() => null)) as { error?: string; message?: string } | null;
  return new ApiError(response.status, body?.error ?? "http_error", body?.message ?? `The server answered ${response.status}.`);
}

const jsonBody = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export function createHttpApi({ baseUrl, token, fetch: fetchImpl = fetch }: HttpApiOptions): Api {
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body) headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetchImpl(`${baseUrl}/v1${path}`, { ...init, headers, cache: "no-store" });
    if (!response.ok) throw await errorFrom(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async function orNull<T>(load: Promise<T>): Promise<T | null> {
    try {
      return await load;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }

  const scanPath = (scanId: string) => `/scans/${encodeURIComponent(scanId)}`;
  const sharesPath = (scanId: string) => `${scanPath(scanId)}/shares`;

  return {
    login: (email, password) => request<AuthResponse>("/auth/login", jsonBody("POST", { email, password })),
    register: (email, password) => request<AuthResponse>("/auth/register", jsonBody("POST", { email, password })),
    logout: () => request<void>("/auth/logout", { method: "POST" }),
    deleteAccount: () => request<void>("/me", { method: "DELETE" }),
    listScans: () => request<Scan[]>("/scans"),
    getScan: (scanId) => orNull(request<Scan>(scanPath(scanId))),
    updateScan: (scanId, changes) => request<Scan>(scanPath(scanId), jsonBody("PATCH", changes)),
    deleteScan: (scanId) => request<void>(scanPath(scanId), { method: "DELETE" }),
    getScene: (scanId) => orNull(request<Scene>(`${scanPath(scanId)}/scene`)),
    getReport: (scanId) => orNull(request<Report>(`${scanPath(scanId)}/assessment`)),
    listAnswers: (scanId) => request<Answer[]>(`${scanPath(scanId)}/answers`),
    saveAnswers: (scanId, answers) => request<Report>(`${scanPath(scanId)}/answers`, jsonBody("PUT", { answers })),
    createLiveTicket: (scanId) => request<LiveTicket>(`${scanPath(scanId)}/live-ticket`, { method: "POST" }),
    createShare: (scanId) => request<Share>(sharesPath(scanId), { method: "POST" }),
    listShares: (scanId) => request<Share[]>(sharesPath(scanId)),
    deleteShare: (scanId, shareToken) => request<void>(`${sharesPath(scanId)}/${encodeURIComponent(shareToken)}`, { method: "DELETE" }),
    getShared: (shareToken) => orNull(request<SharedShop>(`/shared/${encodeURIComponent(shareToken)}`)),
  };
}

/** The API for this deployment: the bundled sample shop in fixture mode, sp-server otherwise. */
export function getApi(token?: string | null): Api {
  return isFixtureMode() ? fixtureApi : createHttpApi({ baseUrl: apiBaseUrl(), token });
}
