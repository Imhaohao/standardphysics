/**
 * Runtime switches, all read from env vars (documented in web/README.md):
 * - NEXT_PUBLIC_SP_FIXTURES=1 renders the bundled sample shop and never calls the API.
 * - NEXT_PUBLIC_SP_API_URL is sp-server's origin, for example https://api.standardphysics.com.
 */
export function isFixtureMode() {
  return process.env.NEXT_PUBLIC_SP_FIXTURES === "1";
}

export function apiBaseUrl() {
  return (process.env.NEXT_PUBLIC_SP_API_URL ?? "http://localhost:8080").replace(/\/$/, "");
}

export function liveSocketUrl(baseUrl: string, scanId: string, token: string) {
  const url = new URL(`/v1/scans/${encodeURIComponent(scanId)}/live`, baseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("role", "viewer");
  url.searchParams.set("token", token);
  return url.toString();
}
