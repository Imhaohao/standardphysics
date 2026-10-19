import type { Scene } from "@/lib/scene/types";
import { apiBaseUrl, isFixtureMode } from "./config";
import { fixtureApi } from "./fixtureApi";
import type { AuthResponse, LiveTicket, Report, Scan } from "./types";

/** Everything the web app asks of sp-server. Pages talk to this interface only. */
export interface Api {
  login(email: string, password: string): Promise<AuthResponse>;
  logout(): Promise<void>;
  listScans(): Promise<Scan[]>;
  getScan(scanId: string): Promise<Scan | null>;
  getScene(scanId: string): Promise<Scene | null>;
  getReport(scanId: string): Promise<Report | null>;
  createLiveTicket(scanId: string): Promise<LiveTicket>;
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

  return {
    login: (email, password) => request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
    logout: () => request<void>("/auth/logout", { method: "POST" }),
    listScans: () => request<Scan[]>("/scans"),
    getScan: (scanId) => orNull(request<Scan>(scanPath(scanId))),
    getScene: (scanId) => orNull(request<Scene>(`${scanPath(scanId)}/scene`)),
    getReport: (scanId) => orNull(request<Report>(`${scanPath(scanId)}/assessment`)),
    createLiveTicket: (scanId) => request<LiveTicket>(`${scanPath(scanId)}/live-ticket`, { method: "POST" }),
  };
}

/** The API for this deployment: the bundled sample shop in fixture mode, sp-server otherwise. */
export function getApi(token?: string | null): Api {
  return isFixtureMode() ? fixtureApi : createHttpApi({ baseUrl: apiBaseUrl(), token });
}
